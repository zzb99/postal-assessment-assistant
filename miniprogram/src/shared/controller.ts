import { beijingToday } from './format';
import { reuseRequestId } from './ids';
import {
  buildPayload, composeRequest, continueRequest, deriveView, draftOf, fillReducer, generateBlocker, identityRecord,
  initialState, newForm, packProposal, sanitizeDraft, sanitizeIdentity, selectRequest, unpackProposal,
} from './fill';
import type { EditableField, FillEvent, FillState, FillView, Mode } from './fill';
import type { Composition, ConditionQuestion, KeyValueStore, QuickApi, QuickConfig, QuickRecord } from './types';

/** 存储键沿用旧网页的命名，升级后本机凭证、班组姓名和未完成草稿都能继续使用。 */
export const STORAGE_KEYS = {
  device: 'assessment-quick-device',
  identity: 'assessment-quick-person',
  draft: 'assessment-quick-unfinished-v1',
  request: 'assessment-quick-request-v2',
  proposal: 'assessment-quick-proposal-v2',
} as const;

export type ControllerDeps = {
  api: QuickApi;
  /** 长期存储：班组姓名、草稿、幂等请求键。 */
  store: KeyValueStore;
  /** 短期存储：AI 签名（网页用 sessionStorage；小程序没有会话存储，靠 45 分钟有效期约束）。 */
  sessionStore: KeyValueStore;
  deviceToken: string;
  randomUuid: () => Promise<string>;
  now?: () => number;
};

export type FillSnapshot = { state: FillState; view: FillView; config: QuickConfig | null; storageOk: boolean };

function errorText(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

/**
 * 职工填报流程控制器：负责状态流转、AI 调用、幂等提交与本机保存。
 * 小程序页面和网页组件都只订阅快照并调用这些方法，平台差异只在 api/store 的实现里。
 */
export class FillController {
  private state: FillState;
  private config: QuickConfig | null = null;
  private snapshot: FillSnapshot;
  private listeners: Array<() => void> = [];
  private aiSequence = 0;
  private disposed = false;
  private storageOk = true;
  private saved: Record<string, string> = {};

  constructor(private readonly deps: ControllerDeps) {
    const now = this.now();
    const identity = sanitizeIdentity(deps.store.get(STORAGE_KEYS.identity));
    const draft = sanitizeDraft(deps.store.get(STORAGE_KEYS.draft));
    const mode: Mode = draft.mode || 'ai';
    delete draft.mode;
    const form = newForm(beijingToday(now), identity, draft);
    let state = initialState(form, mode);
    const restored = mode === 'ai' ? unpackProposal(deps.sessionStore.get(STORAGE_KEYS.proposal), deps.deviceToken, form, now) : null;
    if (restored) state = { ...state, form: { ...form, ai_proposal: restored.token }, signedContent: restored.signedContent };
    this.state = state;
    this.snapshot = this.makeSnapshot();
  }

  readonly getSnapshot = (): FillSnapshot => this.snapshot;

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.push(listener);
    return () => { this.listeners = this.listeners.filter((item) => item !== listener); };
  };

  dispatch(event: FillEvent): void {
    if (this.disposed) return;
    const next = fillReducer(this.state, event);
    if (next === this.state) return;
    this.state = next;
    this.persist();
    this.emit();
  }

  setField(key: EditableField, value: string): void { this.dispatch({ type: 'field', key, value }); }

  setMode(mode: Mode): void { this.dispatch({ type: 'mode', mode }); }

  confirm(value: boolean): void { this.dispatch({ type: 'confirm', value }); }

  toggleRules(): void { this.dispatch({ type: 'toggleRules' }); }

  async loadConfig(): Promise<void> {
    try {
      const config = await this.deps.api.config();
      if (this.disposed) return;
      this.config = config;
      const form = this.state.form;
      if (form.unit && !config.units.some((unit) => String(unit.id) === form.unit)) this.setField('unit', '');
      if (config.shifts.length && config.shifts.indexOf(this.state.form.shift) < 0) this.setField('shift', config.shifts[0]);
      if (!config.ai_enabled && this.state.mode === 'ai') this.setMode('manual');
      if (this.state.error.indexOf('无法连接填报服务') === 0) this.dispatch({ type: 'error', message: '' });
      this.emit();
    } catch (cause) {
      this.dispatch({ type: 'error', message: `无法连接填报服务：${errorText(cause, '请稍后重试。')}` });
    }
  }

  async compose(): Promise<void> {
    if (this.state.aiPending || this.state.submitting || this.state.mode !== 'ai') return;
    if (!this.config || !this.config.ai_enabled) { this.dispatch({ type: 'aiMessage', message: '服务器尚未配置AI，请改为手动填写。' }); return; }
    const request = composeRequest(this.state.form);
    if ('error' in request) { this.dispatch({ type: 'aiMessage', message: request.error }); return; }
    await this.runAi('compose', () => this.deps.api.compose(request.body));
  }

  async answer(question: ConditionQuestion, value: boolean | number): Promise<void> {
    if (this.state.aiPending || this.state.submitting) return;
    const request = continueRequest(this.state.composition, { [question.id]: value });
    if ('error' in request) { this.dispatch({ type: 'aiMessage', message: request.error }); return; }
    await this.runAi('refine', () => this.deps.api.continue(request.body));
  }

  async choose(ruleId: string, pricingId: string): Promise<void> {
    if (this.state.aiPending || this.state.submitting) return;
    const request = selectRequest(this.state.composition, ruleId, pricingId);
    if ('error' in request) { this.dispatch({ type: 'aiMessage', message: request.error }); return; }
    await this.runAi('refine', () => this.deps.api.select(request.body));
  }

  /** 正式生成。成功后表单重置为下一张（保留班组、姓名、日期、班次和公司），返回正式记录。 */
  async submit(): Promise<QuickRecord | null> {
    if (this.state.submitting || this.state.aiPending) return null;
    const config = this.config;
    const blocker = generateBlocker(this.state, config);
    if (blocker || !config) { this.dispatch({ type: 'error', message: blocker || '正在连接填报服务…' }); return null; }
    this.dispatch({ type: 'submitStart' });
    try {
      let payload = buildPayload(this.state.form, config);
      if (this.state.mode === 'ai' && this.state.form.assessment_content !== this.state.signedContent) {
        // 使用者改过 AI 正文：先让后端核对修改范围并重新签名。
        const original = { ...payload, assessment_content: this.state.signedContent.trim(), request_id: await this.deps.randomUuid() };
        const confirmed = await this.deps.api.reconfirm({ original, edited_content: payload.assessment_content, facts_confirmed: true });
        if (this.disposed) return null;
        this.dispatch({ type: 'reconfirmed', token: confirmed.proposal_token });
        payload = { ...payload, ai_proposal: confirmed.proposal_token };
      }
      const stored = reuseRequestId(payload as unknown as Record<string, unknown>, this.deps.store.get(STORAGE_KEYS.request), await this.deps.randomUuid());
      this.deps.store.set(STORAGE_KEYS.request, stored);
      const record = await this.deps.api.submit({ ...payload, request_id: stored.requestId });
      if (this.disposed) return record;
      this.dispatch({ type: 'submitDone' });
      this.reset();
      return record;
    } catch (cause) {
      if (!this.disposed) this.dispatch({ type: 'submitFail', message: errorText(cause, '生成失败，填写内容仍然保留，可以重试。') });
      return null;
    }
  }

  /** 开始新的一张：清除幂等键和 AI 签名，保留班组、姓名、日期、班次和公司。 */
  reset(): void {
    this.aiSequence += 1;
    this.deps.store.remove(STORAGE_KEYS.request);
    this.deps.sessionStore.remove(STORAGE_KEYS.proposal);
    delete this.saved[STORAGE_KEYS.proposal];
    this.dispatch({ type: 'reset', today: beijingToday(this.now()) });
    if (this.config && !this.config.ai_enabled) this.setMode('manual');
  }

  dispose(): void {
    this.disposed = true;
    this.aiSequence += 1;
    this.listeners = [];
  }

  private async runAi(kind: 'compose' | 'refine', call: () => Promise<Composition>): Promise<void> {
    const sequence = ++this.aiSequence;
    this.dispatch({ type: 'aiStart', kind });
    try {
      const result = await call();
      if (this.disposed || sequence !== this.aiSequence) return;
      this.dispatch({ type: 'aiDone', result });
    } catch (cause) {
      if (this.disposed || sequence !== this.aiSequence) return;
      this.dispatch({ type: 'aiFail', message: errorText(cause, 'AI暂时不可用，描述已保留，请稍后重试。') });
    }
  }

  private now(): number {
    return this.deps.now ? this.deps.now() : Date.now();
  }

  /** 只在内容变化时写存储，避免每次输入都同步写盘。 */
  private write(store: KeyValueStore, key: string, value: unknown): boolean {
    const text = JSON.stringify(value);
    if (this.saved[key] === text) return true;
    const ok = store.set(key, value);
    if (ok) this.saved[key] = text;
    return ok;
  }

  private persist(): void {
    const identityOk = this.write(this.deps.store, STORAGE_KEYS.identity, identityRecord(this.state.form));
    const draftOk = this.write(this.deps.store, STORAGE_KEYS.draft, draftOf(this.state));
    const packed = packProposal(this.deps.deviceToken, this.state, this.now());
    const proposalKey = packed ? `${packed.context}|${packed.token}|${packed.signedContent}` : '';
    if (!packed) {
      if (this.saved[STORAGE_KEYS.proposal] !== '') { this.deps.sessionStore.remove(STORAGE_KEYS.proposal); this.saved[STORAGE_KEYS.proposal] = ''; }
    } else if (this.saved[STORAGE_KEYS.proposal] !== proposalKey && this.deps.sessionStore.set(STORAGE_KEYS.proposal, packed)) {
      this.saved[STORAGE_KEYS.proposal] = proposalKey;
    }
    this.storageOk = identityOk && draftOk;
  }

  private emit(): void {
    this.snapshot = this.makeSnapshot();
    for (const listener of this.listeners.slice()) listener();
  }

  private makeSnapshot(): FillSnapshot {
    return { state: this.state, view: deriveView(this.state, this.config), config: this.config, storageOk: this.storageOk };
  }
}
