/**
 * 免登录填报接口 /api/quick/* 的数据结构。
 * 小程序与职工网页共用；本目录只能放纯 TypeScript，不得引用 wx、window、document 等平台对象。
 */

export type QuickUnit = { id: number; name: string };

export type QuickConfig = {
  units: QuickUnit[];
  shifts: string[];
  ai_enabled: boolean;
  regulation_version: string;
};

export type ConditionQuestion = { id: string; question: string; kind: string };

export type PricingOption = { id: string; label: string; automatic: boolean };

export type CandidateRule = { id: string; clause: string; original: string; pricing_options?: PricingOption[] };

/** /ai/compose、/ai/continue、/ai/select 的返回值。金额为后端 Decimal 序列化后的字符串。 */
export type Composition = {
  ready: boolean;
  rule_id?: string | null;
  pricing_id?: string | null;
  quantity: number | null;
  penalty_amount: string | null;
  assessment_content: string | null;
  confidence?: string;
  reason: string;
  clarifications: string[];
  regulation_version: string | null;
  proposal_token?: string | null;
  draft_content?: string | null;
  continuation_token?: string | null;
  condition_questions?: ConditionQuestion[];
  candidate_rules?: CandidateRule[];
  local_cache_hit?: boolean;
  disposition?: string;
  writing_notice?: string | null;
};

export type RecordStatus = 'draft' | 'effective' | 'voided';

export type QuickRecord = {
  id: number;
  assessment_no: string | null;
  incident_date: string;
  shift: string;
  team: string;
  assessment_unit_id: number | null;
  assessment_unit_name_snapshot: string;
  inspector_name: string;
  quantity: number;
  assessment_content: string;
  penalty_amount: string;
  penalty_amount_cn: string;
  status: RecordStatus;
  created_at: string;
  updated_at: string;
  finalized_at: string | null;
  voided_at: string | null;
  void_reason: string | null;
};

export type RecordPage = { items: QuickRecord[]; total: number; page: number; page_size: number };

export type ComposeBody = { incident_date: string; shift: string; assessment_unit_id: number; facts: string };

export type ContinueBody = { continuation_token: string; answers: Record<string, boolean | number> };

export type SelectBody = { continuation_token: string; rule_id: string; pricing_id: string };

export type SubmitPayload = {
  incident_date: string;
  shift: string;
  team: string;
  inspector_name: string;
  assessment_unit_id: number;
  assessment_unit_name: string;
  quantity: number;
  penalty_amount: string;
  assessment_content: string;
  ai_proposal?: string;
};

export type ReconfirmBody = {
  original: SubmitPayload & { request_id: string };
  edited_content: string;
  facts_confirmed: true;
};

/** 平台各自实现的接口调用（小程序用 wx.request，网页用 fetch），失败时抛出带中文说明的 Error。 */
export type QuickApi = {
  config(): Promise<QuickConfig>;
  compose(body: ComposeBody): Promise<Composition>;
  continue(body: ContinueBody): Promise<Composition>;
  select(body: SelectBody): Promise<Composition>;
  reconfirm(body: ReconfirmBody): Promise<{ proposal_token: string }>;
  submit(payload: SubmitPayload & { request_id: string }): Promise<QuickRecord>;
  records(page: number): Promise<RecordPage>;
};

/** 平台各自实现的键值存储。读写失败不能阻止填报，因此 set 返回是否成功。 */
export type KeyValueStore = {
  get(key: string): unknown;
  set(key: string, value: unknown): boolean;
  remove(key: string): void;
};

export type DocumentKind = 'word' | 'pdf' | 'png';
