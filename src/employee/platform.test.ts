import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { STORAGE_KEYS } from '@shared/controller';
import { NETWORK_ERROR } from '@shared/errors';
import type { QuickRecord } from '@shared/types';
import { deviceToken, documentFile, resetDeviceForTests, shareFile, webApi, webStore } from './platform';

function fakeStorage(initial: Record<string, string> = {}, broken = false) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { if (broken) throw new DOMException('quota', 'QuotaExceededError'); values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}

const record = { id: 3, assessment_no: 'KH-202611-0003', updated_at: '2026-11-23T01:00:00Z' } as QuickRecord;

beforeEach(() => {
  resetDeviceForTests();
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: fakeStorage() });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('browser storage', () => {
  it('reads legacy raw strings and JSON values', () => {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: fakeStorage({ raw: 'abc', json: '{"team":"二班"}' }) });
    const store = webStore('localStorage');
    expect(store.get('raw')).toBe('abc');
    expect(store.get('json')).toEqual({ team: '二班' });
    expect(store.set('json', { team: '三班' })).toBe(true);
    expect(store.get('json')).toEqual({ team: '三班' });
  });

  it('falls back to memory and reports failure when storage is blocked', () => {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: fakeStorage({}, true) });
    const store = webStore('localStorage');
    expect(store.set('draft', { facts: '事实' })).toBe(false);
    expect(store.get('draft')).toEqual({ facts: '事实' });
  });

  it('keeps the legacy device credential so old records stay visible', () => {
    const legacy = 'a'.repeat(64);
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: fakeStorage({ [STORAGE_KEYS.device]: legacy }) });
    expect(deviceToken(webStore('localStorage'))).toBe(legacy);
  });

  it('creates a 256-bit credential stored as a raw string', () => {
    const storage = fakeStorage();
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
    const token = deviceToken(webStore('localStorage'));
    expect(token).toMatch(/^[a-f0-9]{64}$/);
    expect(storage.values.get(STORAGE_KEYS.device)).toBe(token);
  });
});

describe('quick api over fetch', () => {
  it('sends the device credential and JSON body', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await webApi.submit({ incident_date: '2026-11-23', shift: '白班', team: '二班', inspector_name: '张三', assessment_unit_id: 1, assessment_unit_name: '华洋公司', quantity: 1, penalty_amount: '100', assessment_content: '正文', request_id: 'r' });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/quick/assessments');
    expect(init.method).toBe('POST');
    expect(new Headers(init.headers).get('X-Device-Token')).toMatch(/^[a-f0-9]{64}$/);
    expect(JSON.parse(String(init.body))).toMatchObject({ team: '二班', request_id: 'r' });
  });

  it('turns server and network failures into readable messages', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: '考核正文金额与填写金额不一致' }), { status: 422 })));
    await expect(webApi.config()).rejects.toThrow('考核正文金额与填写金额不一致');
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    await expect(webApi.config()).rejects.toThrow(NETWORK_ERROR);
  });
});

describe('documents and sharing', () => {
  it('downloads each document once and retries after a failure', async () => {
    let fail = true;
    const fetchMock = vi.fn(async () => (fail ? new Response(JSON.stringify({ detail: '文书队列已满' }), { status: 503 }) : new Response(new Blob(['png']), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);
    await expect(documentFile(record, 'png')).rejects.toThrow('文书队列已满');
    fail = false;
    const file = await documentFile(record, 'png');
    expect(file.name).toBe('KH-202611-0003.png');
    expect(file.type).toBe('image/png');
    await documentFile(record, 'png');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect((fetchMock.mock.calls[1] as unknown as [string])[0]).toBe('/api/quick/assessments/3/documents/png');
  });

  it('reports unsupported, cancelled and shared outcomes', async () => {
    const file = new File(['x'], 'a.png', { type: 'image/png' });
    expect(await shareFile(file, {})).toBe('unsupported');
    expect(await shareFile(file, { canShare: () => false, share: vi.fn() })).toBe('unsupported');
    expect(await shareFile(file, { canShare: () => true, share: async () => { throw new DOMException('cancel', 'AbortError'); } })).toBe('cancelled');
    expect(await shareFile(file, { canShare: () => true, share: async () => undefined })).toBe('shared');
  });
});
