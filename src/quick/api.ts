import { getDeviceToken } from './identity';

function message(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object' || !('detail' in body)) return fallback;
  if (typeof body.detail === 'string') return body.detail;
  if (Array.isArray(body.detail)) return '请检查必填项、数量和金额（必须为正整数）。';
  return fallback;
}

export async function quickApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('X-Device-Token', getDeviceToken());
  if (options.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api/quick${path}`, { ...options, headers, cache: 'no-store' });
  if (!response.ok) throw new Error(message(await response.json().catch(() => null), '保存失败，请稍后重试。'));
  return response.json() as Promise<T>;
}

export async function quickFile(id: number, kind: 'word' | 'pdf', filename: string, signal?: AbortSignal): Promise<File> {
  const response = await fetch(`/api/quick/assessments/${id}/documents/${kind}`, { headers: { 'X-Device-Token': getDeviceToken() }, cache: 'no-store', signal });
  if (!response.ok) throw new Error(message(await response.json().catch(() => null), '文件读取失败，请重试。'));
  return new File([await response.blob()], filename, { type: kind === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
}
