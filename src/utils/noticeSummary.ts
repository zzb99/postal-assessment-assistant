import type { AssessmentForm, AssessmentRule, PricingOption } from '../types';
import { formatDate } from './currency';

// The assessment-item cell is part of the user's original one-page template.
// Keep its content faithful to the operator's entered facts instead of turning
// it into a shortened AI/rule summary.
export const MAX_NOTICE_SUMMARY_LENGTH = 420;

export function buildNoticeSummary(form: AssessmentForm, rule: AssessmentRule, pricing: PricingOption, amount: number) {
  const fact = form.fact.trim().replace(/[。！？!?]+$/, '');
  const unitPrice = pricing.unitPrice ?? 0;
  const heading = `${formatDate(form.date)}${form.shift}巡查发现：${form.company}`;
  return `${heading}${fact}。根据《西安邮区中心邮件处理中心生产质量考核办法》${rule.clause}规定，考核${form.company}，按每${pricing.unit}${unitPrice}元的标准执行，涉及${Number(form.quantity)}${pricing.unit}，共计${amount}元，并承担后续责任。\n\n望${form.company}加强作业人员责任心，避免此类情况再次发生。`;
}
