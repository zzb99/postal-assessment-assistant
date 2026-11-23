import { FillController, STORAGE_KEYS } from '@shared/controller';
import { apiErrorMessage, NETWORK_ERROR } from '@shared/errors';
import { documentFileName, mergeRecent } from '@shared/format';
import { isDeviceToken, toHex, uuidFromBytes } from '@shared/ids';
import type { DocumentKind, KeyValueStore, QuickApi, QuickRecord, RecordPage } from '@shared/types';

type StorageKind = 'localStorage' | 'sessionStorage';

function storageOf(kind: StorageKind): Storage | null {
  try {
    return (globalThis as unknown as Record<StorageKind, Storage | undefined>)[kind] ?? null;
  } catch {
    return null; // 部分浏览器在禁用存储时访问即抛错
  }
}

/** 旧网页把本机凭证存成原始字符串，不是 JSON；读不出 JSON 时按原值返回。 */
function decode(raw: string): unknown {
  try { return JSON.parse(raw); } catch { return raw; }
}

/** 浏览器存储；被禁用时退回内存（关闭页面即丢失），set 返回 false 让界面提示。 */
export function webStore(kind: StorageKind): KeyValueStore {
  const memory = new Map<string, string>();
  return {
    get(key) {
      const cached = memory.get(key);
      if (cached !== undefined) return decode(cached);
      try {
        const raw = storageOf(kind)?.getItem(key) ?? null;
        return raw === null ? null : decode(raw);
      } catch {
        return null;
      }
    },
    set(key, value) {
      const text = JSON.stringify(value);
      try {
        const storage = storageOf(kind);
        if (storage) { storage.setItem(key, text); memory.delete(key); return true; }
      } catch {
        // 写入失败时保存在内存中，至少本次打开期间可用。
      }
      memory.set(key, text);
      return false;
    },
    remove(key) {
      memory.delete(key);
      try { storageOf(kind)?.removeItem(key); } catch { /* 存储不可用 */ }
    },
  };
}

export const localStore = webStore('localStorage');
export const sessionStore = webStore('sessionStorage');

let device = '';

/** 本机凭证沿用旧网页的键和原始字符串格式，升级后原来的本机记录仍可查看。 */
export function deviceToken(store: KeyValueStore = localStore): string {
  if (device) return device;
  const stored = store.get(STORAGE_KEYS.device);
  if (isDeviceToken(stored)) { device = stored; return device; }
  device = toHex(globalThis.crypto.getRandomValues(new Uint8Array(32)));
  try { storageOf('localStorage')?.setItem(STORAGE_KEYS.device, device); } catch { /* 只在本次打开期间有效 */ }
  return device;
}

export function resetDeviceForTests(): void {
  device = '';
}

export async function randomUuid(): Promise<string> {
  return uuidFromBytes(globalThis.crypto.getRandomValues(new Uint8Array(16)));
}

type CallOptions = { method?: 'GET' | 'POST'; body?: unknown; timeoutMs?: number };

async function call<T>(path: string, options: CallOptions = {}): Promise<T> {
  const headers = new Headers({ 'X-Device-Token': deviceToken() });
  if (options.body !== undefined) headers.set('Content-Type', 'application/json');
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), options.timeoutMs ?? 30000);
  let response: Response;
  try {
    response = await fetch(`/api/quick${path}`, {
      method: options.method || 'GET', headers, cache: 'no-store', signal: abort.signal,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new Error(abort.signal.aborted ? '请求超时，填写内容已保留，请稍后重试。' : NETWORK_ERROR);
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) throw new Error(apiErrorMessage(response.status, await response.json().catch(() => null), '请求失败，请稍后重试。'));
  return response.json() as Promise<T>;
}

export const webApi: QuickApi = {
  config: () => call('/config'),
  compose: (body) => call('/ai/compose', { method: 'POST', body, timeoutMs: 60000 }),
  continue: (body) => call('/ai/continue', { method: 'POST', body }),
  select: (body) => call('/ai/select', { method: 'POST', body }),
  reconfirm: (body) => call('/ai/reconfirm', { method: 'POST', body }),
  // 生成需要排队转换 Word/PDF，后端最长等待约 45 秒再加转换时间。
  submit: (payload) => call('/assessments', { method: 'POST', body: payload, timeoutMs: 120000 }),
  records: (page) => call<RecordPage>(`/assessments?page=${page}`),
};

let controller: FillController | null = null;

/** 整个网页只有一个填报控制器，切换「我的记录」再回来，填写内容仍在。 */
export function fillController(): FillController {
  if (!controller) controller = new FillController({ api: webApi, store: localStore, sessionStore, deviceToken: deviceToken(), randomUuid });
  return controller;
}

let cachedRecords: QuickRecord[] = [];

export function rememberRecords(items: QuickRecord[]): void {
  cachedRecords = mergeRecent(cachedRecords, items, 200);
}

export function cachedRecord(id: number): QuickRecord | null {
  return cachedRecords.find((item) => item.id === id) ?? null;
}

export async function loadRecords(page: number): Promise<RecordPage> {
  const result = await webApi.records(page);
  rememberRecords(result.items);
  return result;
}

/** 结果页直接打开（例如刷新）时，在最近几页本机记录里查找。 */
export async function findRecord(id: number): Promise<QuickRecord | null> {
  const cached = cachedRecord(id);
  if (cached) return cached;
  for (let page = 1; page <= 5; page += 1) {
    const result = await loadRecords(page);
    const found = cachedRecord(id);
    if (found || result.items.length < result.page_size) return found;
  }
  return null;
}

const MEDIA: Record<DocumentKind, string> = {
  word: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
  png: 'image/png',
};

const files = new Map<string, Promise<File>>();

/** 读取正式文书（PNG 为服务端由归档 PDF 渲染的分享图片），同一文件只下载一次。 */
export function documentFile(record: QuickRecord, kind: DocumentKind): Promise<File> {
  const key = `${record.id}:${record.updated_at}:${kind}`;
  let pending = files.get(key);
  if (!pending) {
    pending = (async () => {
      let response: Response;
      try {
        response = await fetch(`/api/quick/assessments/${record.id}/documents/${kind}`, { headers: { 'X-Device-Token': deviceToken() }, cache: 'no-store' });
      } catch {
        throw new Error(NETWORK_ERROR);
      }
      if (!response.ok) throw new Error(apiErrorMessage(response.status, await response.json().catch(() => null), '文件读取失败，请重试。'));
      return new File([await response.blob()], documentFileName(record, kind), { type: MEDIA[kind] });
    })();
    files.set(key, pending);
    pending.catch(() => files.delete(key));
  }
  return pending;
}

export function saveFile(file: File): void {
  const url = URL.createObjectURL(file);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = file.name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

type SharePlatform = { share?: (data: ShareData) => Promise<void>; canShare?: (data: ShareData) => boolean };

/** 调起系统分享（安卓 Chrome、iOS Safari 等支持文件分享）；微信内置浏览器不支持，返回 unsupported。 */
export async function shareFile(file: File, platform: SharePlatform = globalThis.navigator): Promise<'shared' | 'unsupported' | 'cancelled'> {
  if (!platform || !platform.share || !platform.canShare || !platform.canShare({ files: [file] })) return 'unsupported';
  try {
    await platform.share({ files: [file], title: file.name });
    return 'shared';
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return 'cancelled';
    throw error;
  }
}

export function inWeChat(): boolean {
  return typeof navigator !== 'undefined' && /MicroMessenger/i.test(navigator.userAgent);
}

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
  } catch {
    // 退回旧方式
  }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand('copy');
    area.remove();
    return copied;
  } catch {
    return false;
  }
}
