import { FillController, STORAGE_KEYS } from '../shared/controller';
import { mergeRecent } from '../shared/format';
import { isDeviceToken, toHex, uuidFromBytes } from '../shared/ids';
import type { DocumentKind, QuickApi, QuickRecord, RecordPage } from '../shared/types';
import { download, randomBytes, request, wxStore } from './wx';

let tokenPromise: Promise<string> | null = null;

/** 本机凭证：首次使用时生成 256 位随机数，保存在微信本地存储；后端只保存其 SHA-256。 */
export function deviceToken(): Promise<string> {
  if (!tokenPromise) {
    tokenPromise = (async () => {
      const stored = wxStore.get(STORAGE_KEYS.device);
      if (isDeviceToken(stored)) return stored;
      const token = toHex(await randomBytes(32));
      wxStore.set(STORAGE_KEYS.device, token);
      return token;
    })();
    tokenPromise.catch(() => { tokenPromise = null; });
  }
  return tokenPromise;
}

export async function randomUuid(): Promise<string> {
  return uuidFromBytes(await randomBytes(16));
}

export function createApi(token: string): QuickApi {
  return {
    config: () => request('/config', token),
    compose: (body) => request('/ai/compose', token, 'POST', body, 60000),
    continue: (body) => request('/ai/continue', token, 'POST', body),
    select: (body) => request('/ai/select', token, 'POST', body),
    reconfirm: (body) => request('/ai/reconfirm', token, 'POST', body),
    // 生成需要排队转换 Word/PDF，后端最长等待约 45 秒再加转换时间。
    submit: (payload) => request('/assessments', token, 'POST', payload, 120000),
    records: (page) => request<RecordPage>(`/assessments?page=${page}`, token),
  };
}

let controllerPromise: Promise<FillController> | null = null;

/** 填报控制器在整个小程序生命周期内只有一个，切换页面不丢失填写内容。 */
export function fillController(): Promise<FillController> {
  if (!controllerPromise) {
    controllerPromise = deviceToken().then((token) => new FillController({
      api: createApi(token), store: wxStore, sessionStore: wxStore, deviceToken: token, randomUuid,
    }));
    controllerPromise.catch(() => { controllerPromise = null; });
  }
  return controllerPromise;
}

let cachedRecords: QuickRecord[] = [];

export function rememberRecords(items: QuickRecord[]): void {
  cachedRecords = mergeRecent(cachedRecords, items, 200);
}

export function cachedRecord(id: number): QuickRecord | null {
  for (const item of cachedRecords) if (item.id === id) return item;
  return null;
}

export async function loadRecords(page: number): Promise<RecordPage> {
  const token = await deviceToken();
  const result = await createApi(token).records(page);
  rememberRecords(result.items);
  return result;
}

/** 结果页直接打开（例如重新进入）时，在最近几页本机记录里查找。 */
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

const files: Record<string, string> = {};

/** 下载并缓存文书临时文件；同一条记录同一种文件只下载一次。 */
export async function documentFile(record: QuickRecord, kind: DocumentKind): Promise<string> {
  const key = `${record.id}:${record.updated_at}:${kind}`;
  if (files[key]) return files[key];
  const path = await download(`/assessments/${record.id}/documents/${kind}`, await deviceToken());
  files[key] = path;
  return path;
}
