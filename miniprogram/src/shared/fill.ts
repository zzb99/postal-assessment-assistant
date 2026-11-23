import { amountToChinese } from './format';
import type { Composition, ComposeBody, ConditionQuestion, ContinueBody, PricingOption, QuickConfig, SelectBody, SubmitPayload } from './types';

/** 与后端 schemas.AssessmentInput / QuickAiRequest 的限制保持一致。 */
export const LIMITS = { team: 32, name: 100, facts: 1000, content: 600, contentLines: 10, quantity: 100000, amount: 100000000 } as const;

export type Mode = 'ai' | 'manual';

export type FillForm = {
  team: string;
  inspector_name: string;
  incident_date: string;
  shift: string;
  /** 被考核公司 id，用字符串便于表单绑定。 */
  unit: string;
  facts: string;
  assessment_content: string;
  quantity: string;
  penalty_amount: string;
  /** 后端对 AI 核定结果的签名；任何影响事实、条款或金额的修改都会使其失效。 */
  ai_proposal: string;
};

export type EditableField = Exclude<keyof FillForm, 'ai_proposal'>;

export type FillState = {
  form: FillForm;
  mode: Mode;
  composition: Composition | null;
  /** AI 区域的状态提示。 */
  message: string;
  /** ai_proposal 签名对应的正文；与当前正文不同说明使用者改过文字。 */
  signedContent: string;
  editConfirmed: boolean;
  showAllRules: boolean;
  aiPending: boolean;
  submitting: boolean;
  /** 页面级错误（连接失败、生成失败等）。 */
  error: string;
};

export type Identity = { team: string; inspector_name: string };

export type FillEvent =
  | { type: 'field'; key: EditableField; value: string }
  | { type: 'mode'; mode: Mode }
  | { type: 'confirm'; value: boolean }
  | { type: 'toggleRules' }
  | { type: 'aiStart'; kind: 'compose' | 'refine' }
  | { type: 'aiDone'; result: Composition }
  | { type: 'aiFail'; message: string }
  | { type: 'aiMessage'; message: string }
  | { type: 'reconfirmed'; token: string }
  | { type: 'submitStart' }
  | { type: 'submitDone' }
  | { type: 'submitFail'; message: string }
  | { type: 'error'; message: string }
  | { type: 'reset'; today: string };

const MAX_LENGTH: Partial<Record<EditableField, number>> = {
  team: LIMITS.team, inspector_name: LIMITS.name, facts: LIMITS.facts, assessment_content: LIMITS.content, quantity: 6, penalty_amount: 12,
};
const CONTEXT_FIELDS: EditableField[] = ['incident_date', 'shift', 'unit'];

export const DRAFT_FIELDS = ['incident_date', 'shift', 'unit', 'facts', 'assessment_content', 'quantity', 'penalty_amount'] as const;
export type DraftField = typeof DRAFT_FIELDS[number];
export type Draft = Partial<Record<DraftField, string>> & { mode?: Mode };

export function newForm(today: string, identity: Identity, keep: Partial<FillForm> = {}): FillForm {
  return {
    team: identity.team, inspector_name: identity.inspector_name, incident_date: today, shift: '白班', unit: '',
    facts: '', assessment_content: '', quantity: '', penalty_amount: '', ai_proposal: '', ...keep,
  };
}

export function initialState(form: FillForm, mode: Mode = 'ai'): FillState {
  return { form, mode, composition: null, message: '', signedContent: '', editConfirmed: false, showAllRules: false, aiPending: false, submitting: false, error: '' };
}

/** 读取本机记住的班组和姓名；兼容旧网页保存的 {team, name}。 */
export function sanitizeIdentity(raw: unknown): Identity {
  if (!raw || typeof raw !== 'object') return { team: '', inspector_name: '' };
  const value = raw as Record<string, unknown>;
  const team = typeof value.team === 'string' ? value.team : '';
  const name = typeof value.inspector_name === 'string' ? value.inspector_name : typeof value.name === 'string' ? value.name : '';
  return { team: team.slice(0, LIMITS.team), inspector_name: name.slice(0, LIMITS.name) };
}

/** 保存格式沿用旧网页的 {team, name}，升级后仍能带出原来记住的信息。 */
export function identityRecord(form: FillForm): { team: string; name: string } {
  return { team: form.team.trim(), name: form.inspector_name.trim() };
}

export function sanitizeDraft(raw: unknown): Draft {
  if (!raw || typeof raw !== 'object') return {};
  const value = raw as Record<string, unknown>;
  const draft: Draft = {};
  for (const key of DRAFT_FIELDS) {
    const item = value[key];
    if (typeof item === 'string' && item.length <= LIMITS.facts) draft[key] = item;
  }
  if (value.mode === 'ai' || value.mode === 'manual') draft.mode = value.mode;
  return draft;
}

/** 草稿只保存可见的输入，永不保存 AI 签名。 */
export function draftOf(state: FillState): Draft {
  const draft: Draft = { mode: state.mode };
  for (const key of DRAFT_FIELDS) draft[key] = state.form[key];
  return draft;
}

/** AI 签名的短期恢复：只在同一设备、同一班组姓名和同一事实/计费上下文下有效。 */
export const PROPOSAL_TTL_MS = 45 * 60 * 1000;
export type SavedProposal = { context: string; token: string; signedContent: string; expires: number };

export function proposalContext(device: string, form: FillForm): string {
  return JSON.stringify([device, form.incident_date, form.shift, form.unit, form.facts, form.quantity, form.penalty_amount, form.team, form.inspector_name]);
}

export function packProposal(device: string, state: FillState, now: number): SavedProposal | null {
  if (!state.form.ai_proposal || state.mode !== 'ai') return null;
  return { context: proposalContext(device, state.form), token: state.form.ai_proposal, signedContent: state.signedContent, expires: now + PROPOSAL_TTL_MS };
}

export function unpackProposal(raw: unknown, device: string, form: FillForm, now: number): { token: string; signedContent: string } | null {
  if (!raw || typeof raw !== 'object') return null;
  const item = raw as Partial<SavedProposal>;
  if (item.context !== proposalContext(device, form) || typeof item.expires !== 'number' || now > item.expires) return null;
  if (typeof item.token !== 'string' || !item.token || typeof item.signedContent !== 'string') return null;
  return { token: item.token, signedContent: item.signedContent };
}

/** AI 结果完整（正文、签名、数量、金额都有）时返回可直接填入表单的值。 */
export function preparedFrom(result: Composition): Pick<FillForm, 'quantity' | 'penalty_amount' | 'assessment_content' | 'ai_proposal'> | null {
  if (!result.ready || !result.assessment_content || !result.proposal_token || !result.quantity || !result.penalty_amount) return null;
  return { quantity: String(result.quantity), penalty_amount: String(result.penalty_amount), assessment_content: result.assessment_content, ai_proposal: result.proposal_token };
}

function pendingMessage(result: Composition): string {
  if (result.condition_questions && result.condition_questions.length) return '已保留正文，请补充下面的现场情况。';
  if (result.disposition === 'choose_rule' && result.candidate_rules && result.candidate_rules.length) return '请核对下方最相关的制度依据，选择符合现场情况的一项。';
  return (result.clarifications && result.clarifications[0]) || result.reason || '正文已保留，条款和金额仍待核对。';
}

function invalidateAi(state: FillState): FillState {
  return { ...state, form: { ...state.form, ai_proposal: '' }, editConfirmed: false };
}

export function fillReducer(state: FillState, event: FillEvent): FillState {
  switch (event.type) {
    case 'field': {
      if (state.aiPending || state.submitting) return state;
      const limit = MAX_LENGTH[event.key];
      const value = limit ? event.value.slice(0, limit) : event.value;
      if (state.form[event.key] === value) return state;
      if (event.key === 'quantity' || event.key === 'penalty_amount') {
        if (state.mode !== 'manual') return state; // AI 核定的数量和金额只读
      }
      if (event.key === 'assessment_content' && state.mode === 'ai' && !state.form.ai_proposal) return state; // 未核定金额的草稿只读
      let next: FillState = { ...state, form: { ...state.form, [event.key]: value }, error: '' };
      if (event.key === 'facts' || CONTEXT_FIELDS.indexOf(event.key) >= 0) {
        next = { ...invalidateAi(next), composition: null, message: '', showAllRules: false };
      } else if (event.key === 'assessment_content' || event.key === 'quantity' || event.key === 'penalty_amount') {
        next.editConfirmed = false;
      }
      return next;
    }
    case 'mode':
      if (state.mode === event.mode || state.aiPending || state.submitting) return state;
      return { ...invalidateAi(state), mode: event.mode, composition: null, message: '', showAllRules: false, error: '' };
    case 'confirm':
      return state.editConfirmed === event.value ? state : { ...state, editConfirmed: event.value };
    case 'toggleRules':
      return { ...state, showAllRules: !state.showAllRules };
    case 'aiStart':
      return { ...invalidateAi(state), aiPending: true, error: '', message: event.kind === 'compose' ? '正在匹配制度并整理正文…' : '正在核算金额…' };
    case 'aiDone': {
      const result = event.result;
      let form: FillForm = { ...state.form, ai_proposal: '' };
      if (result.draft_content) form = { ...form, assessment_content: result.draft_content.slice(0, LIMITS.content), quantity: '', penalty_amount: '' };
      const prepared = preparedFrom(result);
      if (prepared) {
        return { ...state, form: { ...form, ...prepared }, composition: result, signedContent: prepared.assessment_content, editConfirmed: false, aiPending: false, showAllRules: false, message: '正文和金额已整理，请核对后生成。' };
      }
      return { ...state, form, composition: result, aiPending: false, showAllRules: false, message: pendingMessage(result) };
    }
    case 'aiFail':
      return { ...state, aiPending: false, message: event.message };
    case 'aiMessage':
      return { ...state, message: event.message };
    case 'reconfirmed':
      return { ...state, form: { ...state.form, ai_proposal: event.token }, signedContent: state.form.assessment_content };
    case 'submitStart':
      return { ...state, submitting: true, error: '' };
    case 'submitDone':
      return { ...state, submitting: false };
    case 'submitFail':
      return { ...state, submitting: false, error: event.message };
    case 'error':
      return { ...state, error: event.message };
    case 'reset': {
      const { team, inspector_name, shift, unit, incident_date } = state.form;
      return initialState(newForm(event.today, { team, inspector_name }, { shift, unit, incident_date: incident_date || event.today }));
    }
    default:
      return state;
  }
}

/** 正整数（AI 返回的金额可能带 ".00"）。 */
export function isPositiveInteger(text: string, max: number): boolean {
  const value = String(text).trim();
  return /^[1-9]\d*(\.0{1,2})?$/.test(value) && Number(value) <= max;
}

export function contentProblem(content: string): string | null {
  if (content.length > LIMITS.content) return `正文最多${LIMITS.content}字。`;
  if ((content.match(/\n/g) || []).length > LIMITS.contentLines) return `正文最多${LIMITS.contentLines}个换行。`;
  return null;
}

/** 返回不能生成的原因；可以生成时返回 null。 */
export function generateBlocker(state: FillState, config: QuickConfig | null): string | null {
  const form = state.form;
  if (!config) return '正在连接填报服务…';
  if (state.aiPending) return 'AI 正在处理，请稍候。';
  if (!form.team.trim() || !form.inspector_name.trim()) return '请填写班组和姓名。';
  if (!form.incident_date) return '请选择检查日期。';
  if (!form.unit) return '请选择被考核公司。';
  if (state.mode === 'ai') {
    if (!form.assessment_content.trim()) return '先描述现场问题并点击「AI智能整理」，或改为手动填写。';
    if (!form.ai_proposal) return '条款和金额还没核定，请按提示补充情况或选择条款。';
    if (form.assessment_content !== state.signedContent && !state.editConfirmed) return '正文已修改，请勾选确认后再生成。';
  } else if (!form.assessment_content.trim()) return '请填写考核正文。';
  const problem = contentProblem(form.assessment_content);
  if (problem) return problem;
  if (!isPositiveInteger(form.quantity, LIMITS.quantity)) return `数量须为 1 至 ${LIMITS.quantity} 的整数。`;
  if (!isPositiveInteger(form.penalty_amount, LIMITS.amount)) return '考核金额须为正整数（元）。';
  if (state.mode === 'manual' && !state.editConfirmed) return '请勾选「正文、制度依据和金额已核对」。';
  return null;
}

export type RuleView = { id: string; clause: string; original: string; current: boolean; options: PricingOption[] };

export type FillView = {
  blocker: string | null;
  amountCn: string;
  unitIndex: number;
  unitName: string;
  shifts: string[];
  aiEnabled: boolean;
  canCompose: boolean;
  showReview: boolean;
  contentEditable: boolean;
  contentLabel: string;
  contentCount: string;
  amountsVisible: boolean;
  amountsEditable: boolean;
  confirmVisible: boolean;
  confirmText: string;
  question: ConditionQuestion | null;
  rulesVisible: boolean;
  rulesTitle: string;
  rulesOpen: boolean;
  rules: RuleView[];
  hiddenRules: number;
  notice: string;
  submitLabel: string;
};

/** 两个平台的界面都只根据这个纯数据视图渲染。 */
export function deriveView(state: FillState, config: QuickConfig | null): FillView {
  const form = state.form;
  const units = config ? config.units : [];
  let unitIndex = -1;
  for (let index = 0; index < units.length; index += 1) if (String(units[index].id) === form.unit) unitIndex = index;
  const manual = state.mode === 'manual';
  const signed = Boolean(form.ai_proposal);
  const result = manual ? null : state.composition;
  const candidates = (result && result.candidate_rules) || [];
  const choosable = Boolean(result && !result.ready && result.continuation_token);
  const current = candidates.filter((rule) => rule.id === (result && result.rule_id));
  const ordered = current.concat(candidates.filter((rule) => rule.id !== (result && result.rule_id)));
  const visibleCount = state.showAllRules ? ordered.length : Math.min(ordered.length, result && result.ready ? 1 : 3);
  const questions = (result && result.condition_questions) || [];
  return {
    blocker: generateBlocker(state, config),
    amountCn: form.penalty_amount && /^\d+(\.\d{1,2})?$/.test(form.penalty_amount.trim()) ? amountToChinese(form.penalty_amount.trim()) : '待填写金额',
    unitIndex,
    unitName: unitIndex >= 0 ? units[unitIndex].name : '',
    shifts: config && config.shifts.length ? config.shifts : ['白班', '夜班'],
    aiEnabled: Boolean(config && config.ai_enabled),
    canCompose: Boolean(config && config.ai_enabled) && !state.aiPending && !state.submitting,
    showReview: manual || Boolean(form.assessment_content),
    contentEditable: manual || signed,
    contentLabel: manual ? '考核正文 · 手动填写' : signed ? '考核正文 · 可核对修改' : '正文草稿 · 待核定金额',
    contentCount: `${form.assessment_content.length}/${LIMITS.content}`,
    amountsVisible: manual || signed,
    amountsEditable: manual,
    confirmVisible: manual || (signed && form.assessment_content !== state.signedContent),
    confirmText: manual ? '正文、制度依据和金额已核对。' : '修改内容已核对，事实、条款和金额未改变。',
    question: choosable && questions.length ? questions[0] : null,
    rulesVisible: ordered.length > 0,
    rulesTitle: result && result.ready ? '查看本单制度依据' : '相关制度依据与计费标准',
    rulesOpen: Boolean(result && !result.ready && result.disposition === 'choose_rule'),
    rules: ordered.slice(0, visibleCount).map((rule) => ({
      id: rule.id, clause: rule.clause, original: rule.original, current: rule.id === (result && result.rule_id),
      options: choosable ? rule.pricing_options || [] : [],
    })),
    hiddenRules: ordered.length - visibleCount,
    notice: (result && result.writing_notice) || '',
    submitLabel: state.submitting ? '正在生成 Word 与 PDF，请勿重复点击…' : '生成考核单',
  };
}

export function buildPayload(form: FillForm, config: QuickConfig): SubmitPayload {
  let unit = null as QuickConfig['units'][number] | null;
  for (const item of config.units) if (String(item.id) === form.unit) unit = item;
  if (!unit) throw new Error('请选择被考核公司。');
  const payload: SubmitPayload = {
    incident_date: form.incident_date, shift: form.shift, team: form.team.trim(), inspector_name: form.inspector_name.trim(),
    assessment_unit_id: unit.id, assessment_unit_name: unit.name, quantity: Number(form.quantity),
    penalty_amount: form.penalty_amount.trim(), assessment_content: form.assessment_content.trim(),
  };
  if (form.ai_proposal) payload.ai_proposal = form.ai_proposal;
  return payload;
}

export function composeRequest(form: FillForm): { body: ComposeBody } | { error: string } {
  if (!form.unit || !form.incident_date) return { error: '先选择被考核公司和检查日期。' };
  if (form.facts.trim().length < 2) return { error: '请简单描述现场问题，例如“现场抽烟”。' };
  return { body: { incident_date: form.incident_date, shift: form.shift, assessment_unit_id: Number(form.unit), facts: form.facts.trim() } };
}

export function continueRequest(composition: Composition | null, answers: Record<string, boolean | number>): { body: ContinueBody } | { error: string } {
  const token = composition && composition.continuation_token;
  const keys = Object.keys(answers);
  if (!token || !keys.length) return { error: '请先选择需要确认的条件。' };
  for (const key of keys) {
    const value = answers[key];
    if (typeof value === 'number') {
      if (!Number.isInteger(value) || value < 1 || value > LIMITS.quantity) return { error: `计费数量须为1至${LIMITS.quantity}的整数。` };
    } else if (typeof value !== 'boolean') return { error: '条件答案无效。' };
  }
  return { body: { continuation_token: token, answers } };
}

export function selectRequest(composition: Composition | null, ruleId: string, pricingId: string): { body: SelectBody } | { error: string } {
  const token = composition && composition.continuation_token;
  if (!token || !ruleId || !pricingId) return { error: '这条依据已过期，请重新整理。' };
  return { body: { continuation_token: token, rule_id: ruleId, pricing_id: pricingId } };
}
