/**
 * 后端地址。小程序只能访问已备案、已在小程序后台「开发管理 → 服务器域名」配置的 HTTPS 域名
 * （request 合法域名与 downloadFile 合法域名都要加）。
 *
 * - develop（开发者工具/真机调试）：默认连本机后端。开发者工具需勾选「不校验合法域名」；
 *   真机调试请把 127.0.0.1 改成电脑的局域网 IP，并在手机上打开调试模式。
 * - trial / release（体验版、正式版）：必须是正式 HTTPS 域名。
 */
const API_BASES = {
  develop: 'http://127.0.0.1:8000',
  trial: 'https://kaohe.zzb9.cn',
  release: 'https://kaohe.zzb9.cn',
} as const;

type EnvVersion = keyof typeof API_BASES;

export function envVersion(): EnvVersion {
  try {
    const value = wx.getAccountInfoSync().miniProgram.envVersion;
    return value in API_BASES ? value : 'release';
  } catch {
    return 'release';
  }
}

export function apiBase(): string {
  return API_BASES[envVersion()];
}
