import type { AssessmentForm, AssessmentRule, DocumentData, PricingOption } from '../types';
import { amountInChinese, formatDate } from '../utils/currency';
import { buildNoticeSummary } from '../utils/noticeSummary';

export function buildDocumentData(form: AssessmentForm, rule: AssessmentRule, pricing: PricingOption): DocumentData {
  const quantityNumber = Number(form.quantity);
  const amount = quantityNumber * (pricing.unitPrice ?? 0);
  const formattedDate = formatDate(form.date);
  const noticeSummary = buildNoticeSummary(form, rule, pricing, amount);
  return { ...form, rule, pricing, quantityNumber, amount, amountChinese: amountInChinese(amount), formattedDate, noticeSummary, itemText: noticeSummary };
}
