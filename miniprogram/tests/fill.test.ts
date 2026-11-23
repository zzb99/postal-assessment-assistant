import { describe, expect, it } from 'vitest';
import {
  composeRequest, continueRequest, deriveView, fillReducer, generateBlocker, initialState, newForm, packProposal,
  sanitizeDraft, sanitizeIdentity, unpackProposal,
} from '../src/shared/fill';
import type { FillState } from '../src/shared/fill';
import type { Composition, QuickConfig } from '../src/shared/types';

const config: QuickConfig = { units: [{ id: 1, name: '华洋公司' }, { id: 2, name: '联智公司' }], shifts: ['白班', '夜班'], ai_enabled: true, regulation_version: 'TEST' };
const base = (): FillState => initialState(newForm('2026-11-23', { team: '二班', inspector_name: '张三' }, { unit: '1', facts: '现场抽烟' }));
const ready: Composition = {
  ready: true, rule_id: 'official-107', quantity: 1, penalty_amount: '500.00', assessment_content: '2026年11月23日白班巡查发现：华洋公司现场吸烟。',
  proposal_token: 'signed-1', reason: '', clarifications: [], regulation_version: 'TEST', continuation_token: null,
  candidate_rules: [{ id: 'official-050', clause: '第50条', original: '异常邮件' }, { id: 'official-107', clause: '第107条', original: '吸烟' }],
};
const pending: Composition = {
  ready: false, quantity: null, penalty_amount: null, assessment_content: null, reason: '缺少条件', clarifications: [], regulation_version: 'TEST',
  draft_content: '正文草稿', continuation_token: 'cont-1', condition_questions: [{ id: 'is_smoking_area', question: '是否在非吸烟区？', kind: 'boolean' }],
  candidate_rules: [{ id: 'official-107', clause: '第107条', original: '吸烟', pricing_options: [{ id: 'fixed', label: '每次500元', automatic: true }] }],
  disposition: 'confirm',
};

const signed = () => fillReducer(fillReducer(base(), { type: 'aiStart', kind: 'compose' }), { type: 'aiDone', result: ready });

describe('fill reducer', () => {
  it('fills the form from a complete AI result', () => {
    const state = signed();
    expect(state.form).toMatchObject({ quantity: '1', penalty_amount: '500.00', ai_proposal: 'signed-1' });
    expect(state.signedContent).toBe(ready.assessment_content);
    expect(state.message).toContain('请核对后生成');
    expect(generateBlocker(state, config)).toBeNull();
  });

  it('invalidates the AI signature when facts or context change', () => {
    for (const [key, value] of [['facts', '另一件事'], ['unit', '2'], ['shift', '夜班'], ['incident_date', '2026-11-22']] as const) {
      const state = fillReducer(signed(), { type: 'field', key, value });
      expect(state.form.ai_proposal).toBe('');
      expect(state.composition).toBeNull();
    }
    expect(fillReducer(signed(), { type: 'field', key: 'team', value: '三班' }).form.ai_proposal).toBe('signed-1');
  });

  it('keeps AI amounts read-only and locks an unpriced draft', () => {
    expect(fillReducer(signed(), { type: 'field', key: 'penalty_amount', value: '1' }).form.penalty_amount).toBe('500.00');
    const drafted = fillReducer(base(), { type: 'aiDone', result: pending });
    expect(drafted.form.assessment_content).toBe('正文草稿');
    expect(fillReducer(drafted, { type: 'field', key: 'assessment_content', value: '改写' }).form.assessment_content).toBe('正文草稿');
  });

  it('requires confirmation after editing signed text', () => {
    const edited = fillReducer(signed(), { type: 'field', key: 'assessment_content', value: `${ready.assessment_content}请整改。` });
    expect(generateBlocker(edited, config)).toContain('勾选确认');
    expect(deriveView(edited, config).confirmVisible).toBe(true);
    expect(generateBlocker(fillReducer(edited, { type: 'confirm', value: true }), config)).toBeNull();
  });

  it('ignores edits while AI is pending and clears AI state on mode switch', () => {
    const busy = fillReducer(base(), { type: 'aiStart', kind: 'compose' });
    expect(fillReducer(busy, { type: 'field', key: 'facts', value: '变更' })).toBe(busy);
    const manual = fillReducer(signed(), { type: 'mode', mode: 'manual' });
    expect(manual).toMatchObject({ mode: 'manual', composition: null, editConfirmed: false });
    expect(manual.form.ai_proposal).toBe('');
    expect(manual.form.assessment_content).toBe(ready.assessment_content);
  });

  it('validates manual entries before generation', () => {
    let state = fillReducer(base(), { type: 'mode', mode: 'manual' });
    state = fillReducer(state, { type: 'field', key: 'assessment_content', value: '手工正文，考核100元。' });
    state = fillReducer(state, { type: 'field', key: 'quantity', value: '0' });
    state = fillReducer(state, { type: 'field', key: 'penalty_amount', value: '100' });
    expect(generateBlocker(state, config)).toContain('数量');
    state = fillReducer(state, { type: 'field', key: 'quantity', value: '1' });
    expect(generateBlocker(state, config)).toContain('已核对');
    state = fillReducer(state, { type: 'confirm', value: true });
    expect(generateBlocker(state, config)).toBeNull();
    expect(generateBlocker(fillReducer(state, { type: 'field', key: 'assessment_content', value: 'x\n'.repeat(11) }), config)).toContain('换行');
    expect(generateBlocker({ ...state, form: { ...state.form, team: ' ' } }, config)).toContain('班组');
    expect(generateBlocker(state, null)).toContain('连接');
  });

  it('resets for the next notice but keeps person, date, shift and company', () => {
    const next = fillReducer(fillReducer(signed(), { type: 'field', key: 'shift', value: '夜班' }), { type: 'reset', today: '2026-11-24' });
    expect(next.form).toMatchObject({ team: '二班', inspector_name: '张三', unit: '1', shift: '夜班', incident_date: '2026-11-23', facts: '', ai_proposal: '' });
    expect(next.mode).toBe('ai');
  });
});

describe('derived view', () => {
  it('shows one question and choosable pricing options for a pending result', () => {
    const view = deriveView(fillReducer(base(), { type: 'aiDone', result: pending }), config);
    expect(view.question?.id).toBe('is_smoking_area');
    expect(view.rules[0].options).toHaveLength(1);
    expect(view.contentEditable).toBe(false);
    expect(view.amountsVisible).toBe(false);
    expect(view.unitName).toBe('华洋公司');
  });

  it('puts the selected rule first and hides others behind a toggle when ready', () => {
    const state = signed();
    const view = deriveView(state, config);
    expect(view.rules.map((rule) => rule.id)).toEqual(['official-107']);
    expect(view.rules[0].options).toEqual([]);
    expect(view.hiddenRules).toBe(1);
    expect(deriveView(fillReducer(state, { type: 'toggleRules' }), config).rules).toHaveLength(2);
    expect(view.amountCn).toBe('伍佰元整');
  });
});

describe('requests and persistence helpers', () => {
  it('validates AI requests locally', () => {
    expect(composeRequest({ ...base().form, facts: '烟' })).toEqual({ error: expect.stringContaining('描述') });
    expect(composeRequest(base().form)).toEqual({ body: { incident_date: '2026-11-23', shift: '白班', assessment_unit_id: 1, facts: '现场抽烟' } });
    expect(continueRequest(pending, { billing_quantity: 0 })).toEqual({ error: expect.stringContaining('计费数量') });
    expect(continueRequest(null, { a: true })).toEqual({ error: expect.any(String) });
    expect(continueRequest(pending, { is_smoking_area: true })).toEqual({ body: { continuation_token: 'cont-1', answers: { is_smoking_area: true } } });
  });

  it('never restores a signature from a draft and accepts the legacy identity format', () => {
    expect(sanitizeDraft({ facts: '事实', ai_proposal: 'x', mode: 'manual', quantity: 5 })).toEqual({ facts: '事实', mode: 'manual' });
    expect(sanitizeIdentity({ team: '二班', name: '张三' })).toEqual({ team: '二班', inspector_name: '张三' });
    expect(sanitizeIdentity('bad')).toEqual({ team: '', inspector_name: '' });
  });

  it('restores a saved proposal only for the same device, person and facts before it expires', () => {
    const state = signed();
    const saved = packProposal('d'.repeat(64), state, 1000);
    expect(unpackProposal(saved, 'd'.repeat(64), state.form, 2000)?.token).toBe('signed-1');
    expect(unpackProposal(saved, 'e'.repeat(64), state.form, 2000)).toBeNull();
    expect(unpackProposal(saved, 'd'.repeat(64), { ...state.form, inspector_name: '李四' }, 2000)).toBeNull();
    expect(unpackProposal(saved, 'd'.repeat(64), state.form, 1000 + 46 * 60 * 1000)).toBeNull();
    expect(packProposal('d'.repeat(64), base(), 1000)).toBeNull();
  });
});
