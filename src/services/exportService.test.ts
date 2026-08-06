import { describe, expect, it, vi } from 'vitest';
import { buildDocumentData, fetchTemplate, fileStem } from './exportService';
import { MAX_NOTICE_SUMMARY_LENGTH } from '../utils/noticeSummary';
import type { AssessmentForm, AssessmentRule, PricingOption } from '../types';
const pricing: PricingOption = { id: 'piece', unit: '件', unitPrice: 50, condition: '每件50元' };
const rule: AssessmentRule = { id: 'white', stage: '装车环节', clause: '装车环节第4条', name: '邮件错发、白送', original: '邮件错发、白送，每件50元，每袋500元。', pricingOptions: [pricing], applicableConditions: '测试', followUpResponsibility: '并承担后续责任。', version: '20260701', needsSupervisorReview: false, keywords: [] };
const form: AssessmentForm = { noticeNo: 'KH20260806', date: '2026-08-06', shift: '白班', company: '华洋公司', inspector: '一班吴正一', stage: rule.stage, ruleId: rule.id, pricingId: pricing.id, quantity: '2', fact: '2026年8月6日装车环节发现错发邮件，现场已核实。' };
describe('canonical export data', () => {
  it('uses the original notice wording structure for both Word and PDF template paths', () => { const data = buildDocumentData(form, rule, pricing); expect(data.amount).toBe(100); expect(data.noticeSummary).toContain('2026年8月6日白班巡查发现：华洋公司'); expect(data.noticeSummary).toContain(form.fact); expect(data.noticeSummary).toContain('装车环节第4条'); expect(data.noticeSummary).toContain('共计100元'); expect(data.noticeSummary).toContain('避免此类情况再次发生'); expect(data.noticeSummary.length).toBeLessThanOrEqual(MAX_NOTICE_SUMMARY_LENGTH); expect(fileStem(data)).toContain('KH20260806-华洋公司-2026-08-06'); });
  it('reports a template failure after retry', async () => { const fetcher = vi.fn().mockRejectedValue(new Error('offline')) as unknown as typeof fetch; await expect(fetchTemplate(fetcher)).rejects.toThrow('Word 模板加载失败'); expect(fetcher).toHaveBeenCalledTimes(2); });
});
