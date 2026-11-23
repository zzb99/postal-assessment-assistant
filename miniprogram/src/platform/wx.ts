import { apiBase, envVersion } from '../config';
import { apiErrorMessage, NETWORK_ERROR } from '../shared/errors';
import type { KeyValueStore } from '../shared/types';

/** 小程序本地存储（按微信用户隔离）。读写失败只返回 false，不能阻止填报。 */
export const wxStore: KeyValueStore = {
  get(key) {
    try {
      const value: unknown = wx.getStorageSync(key);
      return value === '' ? null : value;
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      wx.setStorageSync(key, value);
      return true;
    } catch {
      return false;
    }
  },
  remove(key) {
    try {
      wx.removeStorageSync(key);
    } catch {
      // 存储不可用时没有需要清理的内容。
    }
  },
};

/** 密码学安全随机数（基础库 2.17.3 起）。仅开发者工具缺少该接口时，开发版才退回 Math.random。 */
export function randomBytes(length: number): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const fallback = () => {
      if (envVersion() !== 'develop') { reject(new Error('当前微信版本过低，请升级微信后再使用。')); return; }
      const bytes = new Uint8Array(length);
      for (let index = 0; index < length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
      console.warn('开发版使用 Math.random 生成本机凭证，正式版不会这样做');
      resolve(bytes);
    };
    if (typeof wx.getUserCryptoManager !== 'function') { fallback(); return; }
    try {
      wx.getUserCryptoManager().getRandomValues({
        length,
        success: (result) => resolve(new Uint8Array(result.randomValues)),
        fail: fallback,
      });
    } catch {
      fallback();
    }
  });
}

type Method = 'GET' | 'POST';

export function request<T>(path: string, token: string, method: Method = 'GET', data?: object, timeout = 30000): Promise<T> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBase()}/api/quick${path}`,
      method,
      data: data as WechatMiniprogram.IAnyObject | undefined,
      timeout,
      header: { 'X-Device-Token': token, 'Content-Type': 'application/json' },
      success: (response) => {
        if (response.statusCode >= 200 && response.statusCode < 300) resolve(response.data as T);
        else reject(new Error(apiErrorMessage(response.statusCode, response.data, '请求失败，请稍后重试。')));
      },
      fail: (error) => reject(new Error(/timeout/i.test(error.errMsg || '') ? '请求超时，填写内容已保留，请稍后重试。' : NETWORK_ERROR)),
    });
  });
}

const DOWNLOAD_ERRORS: Record<number, string> = {
  401: '本机凭证无效，请关闭后重新打开再试。',
  404: '本机找不到该文书。',
  409: '该文书未正式生成或已作废。',
  429: '操作过于频繁，请稍后再试。',
};

/** 下载文书到临时文件，返回临时路径。 */
export function download(path: string, token: string, timeout = 60000): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: `${apiBase()}/api/quick${path}`,
      header: { 'X-Device-Token': token },
      timeout,
      success: (response) => {
        if (response.statusCode === 200 && response.tempFilePath) resolve(response.tempFilePath);
        else reject(new Error(DOWNLOAD_ERRORS[response.statusCode] || '文件下载失败，请重试。'));
      },
      fail: () => reject(new Error(NETWORK_ERROR)),
    });
  });
}

/** 用户主动取消分享/预览不算错误。 */
export function cancelled(error: unknown): boolean {
  const message = error && typeof error === 'object' && 'errMsg' in error ? String((error as { errMsg: unknown }).errMsg) : '';
  return /cancel/i.test(message);
}

export function toast(title: string): void {
  wx.showToast({ title, icon: 'none', duration: 2500 });
}

/** setData 只提交变化的字段：避免每次输入都把整份状态（含制度原文）传给视图层。 */
export function changedPaths(previous: Record<string, unknown> | null, next: Record<string, unknown>, prefix: string, skip: string | null = null): Record<string, unknown> {
  const changes: Record<string, unknown> = {};
  if (!previous) { changes[prefix] = next; return changes; }
  for (const key of Object.keys(next)) {
    const path = `${prefix}.${key}`;
    if (path === skip) continue;
    const before = previous[key];
    const after = next[key];
    if (before === after) continue;
    if (before && after && typeof before === 'object' && typeof after === 'object' && JSON.stringify(before) === JSON.stringify(after)) continue;
    changes[path] = after;
  }
  return changes;
}
