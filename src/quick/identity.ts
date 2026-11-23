export type Identity = { team: string; name: string };
const IDENTITY_KEY = 'assessment-quick-person';
const DEVICE_KEY = 'assessment-quick-device';
const REQUEST_KEY = 'assessment-quick-request';
let memoryDevice = '';

export function readIdentity(): Identity {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(IDENTITY_KEY) || 'null');
    if (value && typeof value === 'object' && 'team' in value && 'name' in value && typeof value.team === 'string' && typeof value.name === 'string') return { team: value.team.slice(0, 32), name: value.name.slice(0, 100) };
  } catch { /* Local preferences are optional, never prevent filling the form. */ }
  return { team: '', name: '' };
}

export function rememberIdentity(identity: Identity): boolean {
  try { localStorage.setItem(IDENTITY_KEY, JSON.stringify({ team: identity.team.trim(), name: identity.name.trim() })); return true; }
  catch { return false; }
}

export function getDeviceToken(): string {
  try { const existing = localStorage.getItem(DEVICE_KEY); if (existing && /^[a-f0-9]{64}$/.test(existing)) { memoryDevice = existing; return existing; } } catch { /* Use a tab-scoped capability when browser storage is blocked. */ }
  if (!memoryDevice) memoryDevice = [...crypto.getRandomValues(new Uint8Array(32))].map((value) => value.toString(16).padStart(2, '0')).join('');
  try { localStorage.setItem(DEVICE_KEY, memoryDevice); } catch { /* No cross-device lookup by name. */ }
  return memoryDevice;
}

let memoryRequest: { fingerprint: string; requestId: string } | null = null;
export async function requestIdFor(value: unknown): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(value)));
  const fingerprint = [...new Uint8Array(bytes)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  try { const stored = JSON.parse(localStorage.getItem(REQUEST_KEY) || 'null'); if (stored?.fingerprint === fingerprint && typeof stored.requestId === 'string') return stored.requestId; } catch { /* Fall back to this tab's retry key. */ }
  if (memoryRequest?.fingerprint === fingerprint) return memoryRequest.requestId;
  memoryRequest = { fingerprint, requestId: crypto.randomUUID() };
  try { localStorage.setItem(REQUEST_KEY, JSON.stringify(memoryRequest)); } catch { /* A live tab still retries idempotently. */ }
  return memoryRequest.requestId;
}

export function clearRequest(): void {
  memoryRequest = null;
  try { localStorage.removeItem(REQUEST_KEY); } catch { /* Nothing persisted. */ }
}
