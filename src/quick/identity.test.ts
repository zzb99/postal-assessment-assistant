import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearRequest, readIdentity, rememberIdentity, getDeviceToken, requestIdFor } from './identity';

beforeEach(() => { const values = new Map<string, string>(); vi.stubGlobal('localStorage', { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) }); clearRequest(); });
afterEach(() => vi.unstubAllGlobals());
describe('免登录填写人', () => {
  it('填写班组姓名并再次带出，不存账号密码', () => {
    expect(readIdentity()).toEqual({ team: '', name: '' });
    rememberIdentity({ team: '  夜班组  ', name: ' 张 三 ' });
    expect(readIdentity()).toEqual({ team: '夜班组', name: '张 三' });
    expect(getDeviceToken()).toMatch(/^[a-f0-9]{64}$/);
    expect(getDeviceToken()).toBe(getDeviceToken());
  });
  it('损坏或被禁用的存储不会阻止填报', () => {
    vi.stubGlobal('localStorage', { getItem: () => '{bad', setItem: () => { throw new Error('disabled'); } });
    expect(readIdentity()).toEqual({ team: '', name: '' });
    expect(() => rememberIdentity({ team: '自填', name: '自填' })).not.toThrow();
    expect(getDeviceToken()).toMatch(/^[a-f0-9]{64}$/);
  });
  it('相同内容重试使用同一请求标识，主动新建才重置', async () => {
    const first = await requestIdFor({ text: '同样内容' });
    expect(await requestIdFor({ text: '同样内容' })).toBe(first);
    expect(await requestIdFor({ text: '变更内容' })).not.toBe(first);
    clearRequest();
    expect(await requestIdFor({ text: '同样内容' })).not.toBe(first);
  });
});
