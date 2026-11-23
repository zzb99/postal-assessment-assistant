import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { quickApi } from './api';
import { continuationRequest } from './aiContinuation';

type Question = { id: string; question: string; kind: 'boolean' | 'integer' };
export type Composition = {
  ready: boolean; quantity: number | null; penalty_amount: string | null; assessment_content: string | null;
  proposal_token: string | null; reason: string; clarifications: string[]; regulation_version: string | null;
  draft_content?: string | null; continuation_token?: string | null; condition_questions?: Question[];
  candidate_rules?: Array<{ id: string; clause: string; original: string; pricing_options?: Array<{ id: string; label: string; automatic: boolean }> }>; local_cache_hit?: boolean;
  disposition?: string; writing_notice?: string | null;
  rule_id?: string | null;
};
export type PreparedComposition = { quantity: string; penalty_amount: string; assessment_content: string; ai_proposal: string };
type Context = { incident_date: string; shift: string; assessment_unit_id: number };

export function AiComposer({ enabled, disabled, manual, children, context, facts, onFacts, onDraft, onPrepared, onPending, onInvalidate }: {
  enabled: boolean; disabled: boolean; manual: boolean; children: ReactNode; context: Context;
  facts: string; onFacts: (value: string) => void; onDraft: (value: string) => void;
  onPrepared: (value: PreparedComposition) => void; onPending: (value: boolean) => void; onInvalidate: () => void;
}) {
  const [pending, setPending] = useState(false); const [message, setMessage] = useState('');
  const [result, setResult] = useState<Composition | null>(null);
  const [quantity, setQuantity] = useState('');
  const [showAllRules, setShowAllRules] = useState(false);
  const request = useRef(0); const controller = useRef<AbortController | null>(null); const running = useRef(false);
  const contextKey = JSON.stringify(context);
  const previousContext = useRef(contextKey);
  const callbacks = useRef({ onPrepared, onPending, onInvalidate });
  useEffect(() => { callbacks.current = { onPrepared, onPending, onInvalidate }; });
  useEffect(() => {
    request.current++; controller.current?.abort(); running.current = false;
    setPending(false); setMessage(''); setResult(null); setQuantity('');
    callbacks.current.onPending(false);
    if (previousContext.current !== contextKey) callbacks.current.onInvalidate();
    previousContext.current = contextKey;
    return () => { request.current++; controller.current?.abort(); running.current = false; callbacks.current.onPending(false); };
  }, [contextKey]);

  const execute = async (answers?: Record<string, boolean | number>, selection?: { rule_id: string; pricing_id: string }) => {
    if (running.current || disabled || manual || !enabled) return;
    if (!context.assessment_unit_id || !context.incident_date) { setMessage('先选择被考核公司和检查日期。'); return; }
    if (facts.trim().length < 2) { setMessage('请简单描述现场问题，例如“现场抽烟”。'); return; }
    let operation: { path: string; body: object };
    try {
      operation = selection ? { path: '/ai/select', body: { ...selection, continuation_token: result?.continuation_token } } : answers ? continuationRequest(result?.continuation_token || '', answers) : { path: '/ai/compose', body: { ...context, facts: facts.trim() } };
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : '补充信息无效'); return; }
    running.current = true;
    const current = ++request.current; controller.current?.abort(); const abort = new AbortController(); controller.current = abort;
    setPending(true); onPending(true); onInvalidate(); setMessage(answers || selection ? '正在核算金额…' : '正在匹配制度并整理正文…');
    try {
      const value = await quickApi<Composition>(operation.path, { method: 'POST', body: JSON.stringify(operation.body), signal: abort.signal });
      if (current !== request.current) return;
      setResult(value); setQuantity(''); setShowAllRules(false);
      if (value.draft_content) onDraft(value.draft_content);
      if (!value.ready || !value.assessment_content || !value.proposal_token || !value.quantity || !value.penalty_amount) {
        setMessage(value.condition_questions?.length ? '已保留正文，请补充下面的现场情况。' : value.disposition === 'choose_rule' ? '请核对下方最相关的制度依据，选择符合现场情况的一项。' : value.clarifications?.[0] || value.reason || '正文已保留，条款和金额仍待核对。'); return;
      }
      onPrepared({ quantity: String(value.quantity), penalty_amount: value.penalty_amount, assessment_content: value.assessment_content, ai_proposal: value.proposal_token });
      setMessage('正文和金额已整理，请核对后生成。');
    } catch (cause) {
      if (current === request.current) setMessage(cause instanceof Error ? cause.message : 'AI暂时不可用，描述已保留，请稍后重试。');
    } finally {
      if (current === request.current) { running.current = false; setPending(false); onPending(false); }
    }
  };
  const candidates = result?.candidate_rules || [];
  const selected = candidates.find((rule) => rule.id === result?.rule_id);
  const ordered = selected ? [selected, ...candidates.filter((rule) => rule.id !== selected.id)] : candidates;
  const visibleRules = showAllRules ? ordered : ordered.slice(0, result?.ready ? 1 : 3);
  return <section className="quick-ai">
    <div className="quick-step"><span>2</span><strong>描述问题</strong><small>{manual ? '当前为手动填写' : 'AI匹配制度、整理正文'}</small></div>
    {!manual && <>
    <label>简单描述问题<textarea maxLength={1000} value={facts} disabled={disabled || pending} onChange={(event) => { onFacts(event.target.value); onInvalidate(); setMessage(''); setResult(null); setQuantity(''); }} placeholder="例如：现场抽烟；小件机发现遗留1件；卸车完毕后发现遗留邮件。只写事实，不用写条款。" /></label>
    {!enabled && <p className="helper-message">服务端尚未配置DeepSeek密钥，可先手动填写。</p>}
    <button type="button" className="primary" disabled={disabled || pending || !enabled} onClick={() => void execute()}>{pending ? '正在处理…' : 'AI智能整理'}</button>
    {message && <p className="helper-message" role="status">{message}</p>}
    {result?.writing_notice && <details className="quick-notice"><summary>正文整理说明</summary><p>{result.writing_notice}</p></details>}
    </>}
    {children}
    {!manual && !result?.ready && result?.continuation_token && result.condition_questions?.slice(0, 1).map((question) => <div className="quick-clarifications" key={question.id}>
      <strong>{question.question}</strong>
      {question.kind === 'boolean' ? <div className="actions"><button type="button" disabled={disabled || pending} onClick={() => void execute({ [question.id]: true })}>是，确认属实</button><button type="button" disabled={disabled || pending} onClick={() => void execute({ [question.id]: false })}>否</button></div> : <><label>计费数量<input type="number" min={1} max={100000} step={1} inputMode="numeric" value={quantity} disabled={disabled || pending} onChange={(e) => setQuantity(e.target.value)} /></label><button type="button" disabled={disabled || pending || !quantity} onClick={() => void execute({ [question.id]: Number(quantity) })}>确认数量，继续核算</button></>}
      <small>请按现场实际情况选择，系统据此核算金额。</small>
    </div>)}
    {!manual && result && Boolean(candidates.length) && <details className="quick-more" open={result.disposition === 'choose_rule'}><summary>{result.ready ? '查看本单制度依据' : '相关制度依据与计费标准'}</summary>{visibleRules.map((rule) => <section key={rule.id}><strong>{rule.clause}{rule.id === result.rule_id ? ' · 当前条款' : ''}</strong><p>{rule.original}</p>{!result.ready && result.continuation_token && rule.pricing_options?.map((option) => <div className="quick-pricing-option" key={option.id}><p>{option.label}</p><small>{option.automatic ? '按实际情况补全条件后计算金额' : '复杂标准需手动核定金额'}</small><button type="button" disabled={disabled || pending} onClick={() => void execute(undefined, { rule_id: rule.id, pricing_id: option.id })}>选择此条款</button></div>)}</section>)}{ordered.length > (result.ready ? 1 : 3) && <button type="button" onClick={() => setShowAllRules(!showAllRules)}>{showAllRules ? '收起其他条款' : `查看其他相关条款（${ordered.length - visibleRules.length}）`}</button>}</details>}
  </section>;
}
