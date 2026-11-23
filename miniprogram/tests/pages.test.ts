/**
 * 小程序页面冒烟测试：在 Node 里模拟 wx 与 Page()，把真实页面代码跑一遍。
 * 覆盖 setData 增量更新、wx.request/downloadFile 封装、本机凭证、分享与文档打开等胶水逻辑。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { record } from './fixtures';

type Handler = (request: { method: string; data: unknown; header: Record<string, string> }) => { statusCode: number; data: unknown };
type PageConfig = Record<string, unknown> & { data: Record<string, unknown> };
type PageInstance = Record<string, (...args: unknown[]) => unknown> & { data: Record<string, unknown> };

let pageConfig: PageConfig | null = null;
let routes: Record<string, Handler> = {};
let calls: Record<string, unknown[]> = {};

function track(name: string, result: unknown = undefined) {
  return vi.fn((options?: Record<string, unknown>) => {
    (calls[name] ||= []).push(options);
    const success = options && typeof options.success === 'function' ? (options.success as (value: unknown) => void) : null;
    if (success) success(result);
    return undefined;
  });
}

function setPath(target: Record<string, unknown>, path: string, value: unknown) {
  const keys = path.split('.');
  let cursor = target;
  for (const key of keys.slice(0, -1)) {
    if (!cursor[key] || typeof cursor[key] !== 'object') cursor[key] = {};
    cursor = cursor[key] as Record<string, unknown>;
  }
  cursor[keys[keys.length - 1]] = value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

function instantiate(): PageInstance {
  if (!pageConfig) throw new Error('页面没有调用 Page()');
  const instance = { ...pageConfig, data: JSON.parse(JSON.stringify(pageConfig.data)) } as unknown as PageInstance;
  instance.setData = (patch: unknown) => { for (const [path, value] of Object.entries(patch as Record<string, unknown>)) setPath(instance.data, path, value); };
  return instance;
}

function installWx() {
  const storage = new Map<string, unknown>();
  calls = {};
  const wx = {
    getStorageSync: (key: string) => (storage.has(key) ? storage.get(key) : ''),
    setStorageSync: (key: string, value: unknown) => { storage.set(key, JSON.parse(JSON.stringify(value))); },
    removeStorageSync: (key: string) => { storage.delete(key); },
    getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop', appId: 'touristappid' } }),
    getUserCryptoManager: () => ({ getRandomValues: ({ length, success }: { length: number; success: (value: { randomValues: ArrayBuffer }) => void }) => success({ randomValues: new Uint8Array(length).map((_, index) => (index * 37 + 11) % 256).buffer }) }),
    request: vi.fn((options: { url: string; method?: string; data?: unknown; header: Record<string, string>; success: (value: unknown) => void; fail: (value: unknown) => void }) => {
      const path = options.url.replace('http://127.0.0.1:8000/api/quick', '');
      const handler = routes[`${options.method || 'GET'} ${path.split('?')[0]}`];
      if (!handler) { options.fail({ errMsg: 'request:fail not mocked' }); return; }
      options.success(handler({ method: options.method || 'GET', data: options.data, header: options.header }));
    }),
    downloadFile: vi.fn((options: { url: string; header: Record<string, string>; success: (value: unknown) => void }) => {
      const kind = options.url.split('/').pop();
      options.success({ statusCode: 200, tempFilePath: `wxfile://tmp/${kind}` });
    }),
    showToast: track('showToast'),
    navigateTo: track('navigateTo'),
    switchTab: track('switchTab'),
    setNavigationBarTitle: track('setNavigationBarTitle'),
    showLoading: track('showLoading'),
    hideLoading: track('hideLoading'),
    openDocument: track('openDocument'),
    shareFileMessage: track('shareFileMessage'),
    showShareImageMenu: track('showShareImageMenu'),
    previewImage: track('previewImage'),
    setClipboardData: track('setClipboardData'),
    stopPullDownRefresh: track('stopPullDownRefresh'),
  };
  Object.assign(globalThis, { wx, Page: (config: PageConfig) => { pageConfig = config; } });
  return { wx, storage };
}

const config = { units: [{ id: 1, name: '华阳公司' }], shifts: ['白班', '夜班'], ai_enabled: false, regulation_version: '20260819' };

beforeEach(() => {
  vi.resetModules();
  pageConfig = null;
  routes = { 'GET /config': () => ({ statusCode: 200, data: config }) };
});

const input = (key: string, value: string) => ({ detail: { value }, currentTarget: { dataset: { key } } });

describe('mini program fill page', () => {
  it('fills a manual notice, generates it and opens the result page', async () => {
    const { wx, storage } = installWx();
    let submitted: Record<string, unknown> | null = null;
    routes['POST /assessments'] = ({ data, header }) => {
      expect(header['X-Device-Token']).toMatch(/^[a-f0-9]{64}$/);
      submitted = data as Record<string, unknown>;
      return { statusCode: 200, data: record({ id: 1, assessment_no: 'KH-202611-0001', assessment_content: String((data as Record<string, unknown>).assessment_content) }) };
    };
    await import('../src/pages/fill/fill');
    const page = instantiate();
    await page.onLoad();
    expect(page.data.ready).toBe(true);
    expect((page.data.state as { mode: string }).mode).toBe('manual');
    expect(page.data.units).toEqual(config.units);

    page.onInput(input('team', '二班'));
    page.onInput(input('inspector_name', '测试员'));
    page.onUnit({ detail: { value: 0 }, currentTarget: { dataset: {} } });
    page.onInput(input('assessment_content', '现场遗留邮件1件，考核40元。'));
    page.onInput(input('quantity', '1'));
    page.onInput(input('penalty_amount', '40'));
    expect((page.data.view as { blocker: string }).blocker).toContain('已核对');
    expect((page.data.view as { amountCn: string }).amountCn).toBe('肆拾元整');
    page.toggleConfirm();
    expect((page.data.view as { blocker: string | null }).blocker).toBeNull();
    // 输入值同步回视图数据，生成后的重置才能真正清空输入框。
    expect((page.data.state as { form: Record<string, string> }).form).toMatchObject({ team: '二班', penalty_amount: '40' });

    await page.submit();
    expect(submitted).toMatchObject({ team: '二班', inspector_name: '测试员', assessment_unit_id: 1, assessment_unit_name: '华阳公司', quantity: 1, penalty_amount: '40' });
    expect(String((submitted as unknown as Record<string, unknown>).request_id)).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4/);
    expect(calls.navigateTo[0]).toMatchObject({ url: '/pages/result/result?id=1&fresh=1' });
    const form = (page.data.state as { form: Record<string, string> }).form;
    expect(form).toMatchObject({ team: '二班', unit: '1', assessment_content: '', penalty_amount: '' });
    expect(storage.get('assessment-quick-person')).toEqual({ team: '二班', name: '测试员' });
    expect(wx.request).toHaveBeenCalled();
  });

  it('shows the server error and keeps the form when generation fails', async () => {
    installWx();
    routes['POST /assessments'] = () => ({ statusCode: 503, data: { detail: 'Word转PDF超过60秒，文书保持草稿' } });
    await import('../src/pages/fill/fill');
    const page = instantiate();
    await page.onLoad();
    page.onInput(input('team', '二班'));
    page.onInput(input('inspector_name', '测试员'));
    page.onUnit({ detail: { value: 0 }, currentTarget: { dataset: {} } });
    page.onInput(input('assessment_content', '考核40元。'));
    page.onInput(input('quantity', '1'));
    page.onInput(input('penalty_amount', '40'));
    page.toggleConfirm();
    await page.submit();
    expect(calls.showToast[0]).toMatchObject({ title: 'Word转PDF超过60秒，文书保持草稿' });
    expect(calls.navigateTo).toBeUndefined();
    expect((page.data.state as { form: Record<string, string> }).form.penalty_amount).toBe('40');
  });
});

describe('mini program result and records pages', () => {
  it('prepares the image and PDF, then shares and opens documents', async () => {
    const { wx } = installWx();
    routes['GET /assessments'] = () => ({ statusCode: 200, data: { items: [record({ id: 5, assessment_no: 'KH-202611-0005' })], total: 1, page: 1, page_size: 10 } });
    await import('../src/pages/result/result');
    const page = instantiate();
    await page.onLoad({ id: '5', fresh: '1' });
    await vi.waitFor(() => expect(page.data.pdfPath).toBe('wxfile://tmp/pdf'));
    expect(page.data.imagePath).toBe('wxfile://tmp/png');
    expect(page.data.preparing).toBe(false);
    expect(calls.setNavigationBarTitle[0]).toMatchObject({ title: '考核单已生成' });
    expect(vi.mocked(wx.downloadFile).mock.calls[0][0].header['X-Device-Token']).toMatch(/^[a-f0-9]{64}$/);

    page.shareImage();
    expect(calls.showShareImageMenu[0]).toMatchObject({ path: 'wxfile://tmp/png' });
    page.shareFile();
    expect(calls.shareFileMessage[0]).toMatchObject({ filePath: 'wxfile://tmp/pdf', fileName: 'KH-202611-0005.pdf' });
    await page.openWord();
    expect(calls.openDocument[0]).toMatchObject({ filePath: 'wxfile://tmp/word', fileType: 'docx', showMenu: true });
    page.copyText();
    expect(String((calls.setClipboardData[0] as { data: string }).data)).toContain('KH-202611-0005');
  });

  it('does not offer sharing for a voided notice', async () => {
    const { wx } = installWx();
    routes['GET /assessments'] = () => ({ statusCode: 200, data: { items: [record({ id: 6, status: 'voided', void_reason: '录入错误' })], total: 1, page: 1, page_size: 10 } });
    await import('../src/pages/result/result');
    const page = instantiate();
    await page.onLoad({ id: '6' });
    expect(page.data.effective).toBe(false);
    expect(page.data.statusText).toBe('已作废');
    expect(wx.downloadFile).not.toHaveBeenCalled();
  });

  it('lists local records and loads the next page', async () => {
    installWx();
    const pageOne = Array.from({ length: 10 }, (_, index) => record({ id: 20 - index, assessment_no: `KH-202611-00${20 - index}` }));
    routes['GET /assessments'] = ({ method }) => ({ statusCode: 200, data: method === 'GET' ? { items: pageOne, total: 11, page: 1, page_size: 10 } : null });
    await import('../src/pages/records/records');
    const page = instantiate();
    await page.refresh();
    expect((page.data.rows as unknown[]).length).toBe(10);
    expect(page.data.done).toBe(false);
    routes['GET /assessments'] = () => ({ statusCode: 200, data: { items: [record({ id: 9, assessment_no: 'KH-202611-0009' })], total: 11, page: 2, page_size: 10 } });
    await page.onReachBottom();
    const rows = page.data.rows as Array<{ no: string; amount: string; status: string }>;
    expect(rows).toHaveLength(11);
    expect(rows[10]).toMatchObject({ no: 'KH-202611-0009', amount: '¥500.00', status: '已生成' });
    expect(page.data.done).toBe(true);
    page.open({ currentTarget: { dataset: { id: 9 } } });
    expect(calls.navigateTo[0]).toMatchObject({ url: '/pages/result/result?id=9' });
  });
});
