// 本机凭证、请求幂等键等标识的纯函数。随机字节由平台提供（小程序 UserCryptoManager，网页 crypto）。

export function toHex(bytes: ArrayLike<number>): string {
  let text = '';
  for (let index = 0; index < bytes.length; index += 1) text += (bytes[index] & 0xff).toString(16).padStart(2, '0');
  return text;
}

/** 后端只接受 64 位小写十六进制的本机凭证（256 位随机数）。 */
export function isDeviceToken(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
}

/** 用 16 个随机字节生成 RFC 4122 v4 UUID（后端 request_id 字段校验 UUID 格式）。 */
export function uuidFromBytes(bytes: ArrayLike<number>): string {
  if (bytes.length < 16) throw new Error('生成请求编号需要16个随机字节');
  const copy: number[] = [];
  for (let index = 0; index < 16; index += 1) copy.push(bytes[index] & 0xff);
  copy[6] = (copy[6] & 0x0f) | 0x40;
  copy[8] = (copy[8] & 0x3f) | 0x80;
  const hex = toHex(copy);
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** 键排序后的 JSON，用来判断两次提交内容是否相同。 */
export function stableJson(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? 'null';
  if (Array.isArray(value)) return `[${value.map((item) => stableJson(item)).join(',')}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).filter((key) => record[key] !== undefined).sort()
    .map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`).join(',')}}`;
}

export type StoredRequest = { fingerprint: string; requestId: string };

/**
 * 同一内容重试必须沿用同一个 request_id，后端据此保证不重复编号。
 * 指纹不含 ai_proposal：重新签名后的同一内容仍是同一次提交（与后端 payload_hash 口径一致）。
 */
export function reuseRequestId(payload: Record<string, unknown>, stored: unknown, freshId: string): StoredRequest {
  const content: Record<string, unknown> = {};
  for (const key of Object.keys(payload)) if (key !== 'ai_proposal' && key !== 'request_id') content[key] = payload[key];
  const fingerprint = stableJson(content);
  if (stored && typeof stored === 'object') {
    const item = stored as Partial<StoredRequest>;
    if (item.fingerprint === fingerprint && typeof item.requestId === 'string' && item.requestId) return { fingerprint, requestId: item.requestId };
  }
  return { fingerprint, requestId: freshId };
}
