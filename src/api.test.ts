import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, download, getToken, setToken } from './api';

beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal('localStorage', { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
});
afterEach(() => vi.unstubAllGlobals());

describe('过期请求不能注销新会话', () => {
  it('旧token的401不会清掉新token', async () => {
    let respond!: (response: Response) => void;
    vi.stubGlobal('fetch', () => new Promise<Response>((resolve) => { respond = resolve; }));
    setToken('old-local-test-token');
    const pending = api('/auth/me').catch((error: Error) => error.message);
    setToken('new-local-test-token');
    respond(new Response(JSON.stringify({ detail: '旧会话过期' }), { status: 401 }));
    expect(await pending).toBe('旧会话过期');
    expect(getToken()).toBe('new-local-test-token');
  });
  it('当前token的401正常清除会话', async () => {
    vi.stubGlobal('fetch', async () => new Response('{}', { status: 401 }));
    setToken('current-local-test-token');
    await expect(api('/auth/me')).rejects.toThrow();
    expect(getToken()).toBeNull();
  });
  it('退出或换号后旧文件请求不能触发自动下载', async () => {
    let respond!: (response: Response) => void;
    const click = vi.fn();
    vi.stubGlobal('document', { createElement: () => ({ click }) });
    vi.stubGlobal('fetch', () => new Promise<Response>((resolve) => { respond = resolve; }));
    setToken('old-local-test-token');
    const pending = download('/exports/assessment-ledger.xlsx', 'test.xlsx').catch((error: Error) => error.message);
    setToken('new-local-test-token');
    respond(new Response('private-test-file'));
    expect(await pending).toContain('会话已变化');
    expect(click).not.toHaveBeenCalled();
  });
});
