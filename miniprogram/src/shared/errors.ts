export const NETWORK_ERROR = '网络连接失败，请检查网络后重试。';

/** 把后端错误响应转换为给职工看的中文提示。 */
export function apiErrorMessage(status: number, body: unknown, fallback: string): string {
  const detail = body && typeof body === 'object' && 'detail' in body ? (body as { detail: unknown }).detail : undefined;
  if (status === 401) return '本机凭证无效，请关闭后重新打开再试。';
  if (status === 413) return '填报内容过大，请缩短后重试。';
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) return '请检查必填项：数量和金额必须为正整数，正文不超过600字、10个换行。';
  if (status === 429) return '提交过于频繁，请稍后再试。';
  if (status >= 500) return '服务暂时不可用，已填写的内容仍保留，请稍后重试。';
  return fallback;
}
