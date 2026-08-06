import { describe, expect, it } from 'vitest';
import { MAX_FACT_LENGTH, validateForm } from './validation';
import type { AssessmentForm, AssessmentRule, PricingOption } from '../types';

const pricing: PricingOption = { id: 'bag', unit: '袋', unitPrice: 500, condition: '测试' };
const rule: AssessmentRule = { id: 'r', stage: '装车环节', clause: '装车环节第4条', name: '邮件错发、白送', original: '测试', pricingOptions: [pricing], applicableConditions: '测试', followUpResponsibility: '', version: '20260701', needsSupervisorReview: false, keywords: [] };
const complete: AssessmentForm = { noticeNo: 'KH20260806', date: '2026-08-06', shift: '白班', company: '华洋公司', inspector: '一班吴正一', stage: rule.stage, ruleId: rule.id, pricingId: pricing.id, quantity: '1', fact: '2026年8月6日，装车环节发现邮件错发，现场已核实。' };
describe('form validation', () => {
  it('blocks empty mandatory fields', () => expect(Object.keys(validateForm({ ...complete, company: '', inspector: '', stage: '', ruleId: '', pricingId: '', fact: '' }))).toEqual(expect.arrayContaining(['company', 'inspector', 'stage', 'ruleId', 'pricingId', 'fact'])));
  it.each(['0', '-1', '1.5', '', '100001'])('blocks invalid quantity %s', (quantity) => expect(validateForm({ ...complete, quantity }, rule, pricing).quantity).toBeTruthy());
  it('allows per-piece and per-bag selections explicitly', () => { expect(validateForm({ ...complete, pricingId: 'bag' }, rule, pricing)).toEqual({}); expect(pricing.unit).toBe('袋'); });
  it('blocks an overlong fact description', () => expect(validateForm({ ...complete, fact: '甲'.repeat(MAX_FACT_LENGTH + 1) }, rule, pricing).fact).toBeTruthy());
  it('blocks facts that cannot fit when the original notice wording is included', () => expect(validateForm({ ...complete, fact: '甲'.repeat(350) }, rule, pricing).fact).toContain('按原考核单格式生成后超过'));
});
