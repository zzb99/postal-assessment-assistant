import { describe, expect, it, vi } from 'vitest';
import { FillController, STORAGE_KEYS } from '../src/shared/controller';
import type { Composition, KeyValueStore, QuickApi, QuickConfig } from '../src/shared/types';
import { record } from './fixtures';

const device = 'f'.repeat(64);
const config: QuickConfig = { units: [{ id: 1, name: '华洋公司' }], shifts: ['白班', '夜班'], ai_enabled: true, regulation_version: 'TEST' };
const ready: Composition = {
  ready: true, quantity: 1, penalty_amount: '500', assessment_content: 'AI正文。', proposal_token: 'signed-1', reason: '', clarifications: [], regulation_version: 'TEST',
};

function memoryStore(initial: Record<string, unknown> = {}): KeyValueStore & { data: Record<string, unknown>; writes: number } {
  const data: Record<string, unknown> = { ...initial };
  const store = {
    data, writes: 0,
    get: (key: string) => (key in data ? data[key] : null),
    set: (key: string, value: unknown) => { data[key] = JSON.parse(JSON.stringify(value)); store.writes += 1; return true; },
    remove: (key: string) => { delete data[key]; },
  };
  return store;
}

function setup(overrides: Partial<QuickApi> = {}, stored: Record<string, unknown> = {}, aiEnabled = true) {
  let counter = 0;
  const api: QuickApi = {
    config: vi.fn(async () => ({ ...config, ai_enabled: aiEnabled })),
    compose: vi.fn(async () => ready),
    continue: vi.fn(async () => ready),
    select: vi.fn(async () => ready),
    reconfirm: vi.fn(async () => ({ proposal_token: 'signed-2' })),
    submit: vi.fn(async (payload) => record({ assessment_content: payload.assessment_content })),
    records: vi.fn(async () => ({ items: [], total: 0, page: 1, page_size: 10 })),
    ...overrides,
  };
  const store = memoryStore(stored);
  const sessionStore = memoryStore();
  const controller = new FillController({ api, store, sessionStore, deviceToken: device, randomUuid: async () => `00000000-0000-4000-8000-00000000000${++counter}`, now: () => Date.UTC(2026, 10, 23, 2) });
  return { api, store, sessionStore, controller };
}

async function fillAndCompose(controller: FillController) {
  await controller.loadConfig();
  controller.setField('team', '二班');
  controller.setField('inspector_name', '张三');
  controller.setField('unit', '1');
  controller.setField('facts', '现场抽烟');
  await controller.compose();
}

describe('fill controller', () => {
  it('restores the legacy identity and draft from local storage', () => {
    const { controller } = setup({}, { [STORAGE_KEYS.identity]: { team: '一班', name: '王五' }, [STORAGE_KEYS.draft]: { facts: '旧草稿', unit: '1', mode: 'manual' } });
    const { state } = controller.getSnapshot();
    expect(state.form).toMatchObject({ team: '一班', inspector_name: '王五', facts: '旧草稿', unit: '1', incident_date: '2026-11-23' });
    expect(state.mode).toBe('manual');
  });

  it('switches to manual entry when the server has no AI key', async () => {
    const { controller } = setup({}, {}, false);
    await controller.loadConfig();
    expect(controller.getSnapshot().state.mode).toBe('manual');
    expect(controller.getSnapshot().view.aiEnabled).toBe(false);
  });

  it('composes, submits once with an idempotency key and resets for the next notice', async () => {
    const { controller, api, store } = setup();
    const listener = vi.fn();
    controller.subscribe(listener);
    await fillAndCompose(controller);
    expect(controller.getSnapshot().view.blocker).toBeNull();
    const result = await controller.submit();
    expect(result?.assessment_no).toBe('KH-202611-0007');
    const payload = vi.mocked(api.submit).mock.calls[0][0];
    expect(payload).toMatchObject({ team: '二班', inspector_name: '张三', assessment_unit_id: 1, assessment_unit_name: '华洋公司', quantity: 1, penalty_amount: '500', ai_proposal: 'signed-1' });
    expect(payload.request_id).toMatch(/^[0-9a-f-]{36}$/);
    const { state } = controller.getSnapshot();
    expect(state.form).toMatchObject({ team: '二班', unit: '1', facts: '', assessment_content: '', ai_proposal: '' });
    expect(store.data[STORAGE_KEYS.request]).toBeUndefined();
    expect(store.data[STORAGE_KEYS.identity]).toEqual({ team: '二班', name: '张三' });
    expect(listener).toHaveBeenCalled();
  });

  it('re-signs edited AI text before generating', async () => {
    const { controller, api } = setup();
    await fillAndCompose(controller);
    controller.setField('assessment_content', 'AI正文。请加强管理。');
    expect(controller.getSnapshot().view.blocker).toContain('勾选');
    controller.confirm(true);
    await controller.submit();
    expect(vi.mocked(api.reconfirm).mock.calls[0][0]).toMatchObject({ edited_content: 'AI正文。请加强管理。', facts_confirmed: true, original: { assessment_content: 'AI正文。', ai_proposal: 'signed-1' } });
    expect(vi.mocked(api.submit).mock.calls[0][0]).toMatchObject({ assessment_content: 'AI正文。请加强管理。', ai_proposal: 'signed-2' });
  });

  it('keeps the form and reuses the same request id after a failed generation', async () => {
    let attempts = 0;
    const { controller, api } = setup({ submit: vi.fn(async (payload) => { attempts += 1; if (attempts === 1) throw new Error('文书队列已满'); return record({ assessment_content: payload.assessment_content }); }) });
    await fillAndCompose(controller);
    expect(await controller.submit()).toBeNull();
    expect(controller.getSnapshot().state).toMatchObject({ error: '文书队列已满', submitting: false });
    expect(controller.getSnapshot().state.form.ai_proposal).toBe('signed-1');
    await controller.submit();
    const calls = vi.mocked(api.submit).mock.calls;
    expect(calls[1][0].request_id).toBe(calls[0][0].request_id);
  });

  it('ignores a late AI answer after the user starts a new notice', async () => {
    let resolve: (value: Composition) => void = () => undefined;
    const { controller } = setup({ compose: vi.fn(() => new Promise<Composition>((done) => { resolve = done; })) });
    await controller.loadConfig();
    controller.setField('team', '二班'); controller.setField('inspector_name', '张三'); controller.setField('unit', '1'); controller.setField('facts', '现场抽烟');
    const pendingCall = controller.compose();
    expect(controller.getSnapshot().state.aiPending).toBe(true);
    controller.reset();
    resolve(ready);
    await pendingCall;
    expect(controller.getSnapshot().state.form.ai_proposal).toBe('');
    expect(controller.getSnapshot().state.aiPending).toBe(false);
  });

  it('reports a local validation message instead of calling AI with too little text', async () => {
    const { controller, api } = setup();
    await controller.loadConfig();
    controller.setField('unit', '1');
    controller.setField('facts', '烟');
    await controller.compose();
    expect(api.compose).not.toHaveBeenCalled();
    expect(controller.getSnapshot().state.message).toContain('描述');
  });

  it('does not rewrite storage when nothing persisted changed', async () => {
    const { controller, store } = setup();
    await controller.loadConfig();
    controller.setField('team', '二班');
    const writes = store.writes;
    controller.toggleRules();
    expect(store.writes).toBe(writes);
  });

  it('surfaces a connection error and recovers on retry', async () => {
    let fail = true;
    const { controller } = setup({ config: vi.fn(async () => { if (fail) throw new Error('网络连接失败'); return config; }) });
    await controller.loadConfig();
    expect(controller.getSnapshot().state.error).toContain('无法连接填报服务');
    fail = false;
    await controller.loadConfig();
    expect(controller.getSnapshot().state.error).toBe('');
    expect(controller.getSnapshot().config).not.toBeNull();
  });
});
