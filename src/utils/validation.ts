import type { AssessmentForm, AssessmentRule, FieldErrors, PricingOption } from '../types';
import { buildNoticeSummary, MAX_NOTICE_SUMMARY_LENGTH } from './noticeSummary';

export const MAX_QUANTITY = 100000;
export const MAX_PENALTY_AMOUNT = 100000000;
export const MAX_FACT_LENGTH = 420;

export function validateForm(form: AssessmentForm, rule?: AssessmentRule, pricing?: PricingOption, fields?: Array<keyof AssessmentForm>): FieldErrors {
  const shouldCheck = (field: keyof AssessmentForm) => !fields || fields.includes(field);
  const errors: FieldErrors = {};
  if (shouldCheck('date') && !form.date) errors.date = '请选择发生日期。';
  if (shouldCheck('fillDate') && !form.fillDate) errors.fillDate = '请选择填报日期。';
  if (shouldCheck('company') && !form.company.trim()) errors.company = '请选择或输入被考核单位/工段。';
  if (shouldCheck('inspector') && !form.inspector.trim()) errors.inspector = '请输入检查人。';
  if (shouldCheck('stage') && !form.stage) errors.stage = '请选择作业环节。';
  if (shouldCheck('ruleId') && (!form.ruleId || !rule)) errors.ruleId = '请选择违规类型。';
  if (shouldCheck('pricingId') && (!form.pricingId || !pricing)) errors.pricingId = '请明确选择本次适用的计费单位和单价。';
  if (shouldCheck('pricingId') && (pricing?.needsSupervisorReview || pricing?.unitPrice === null)) errors.pricingId = '该条款需主管按原文最终认定，暂不能自动开具。';
  const quantity = Number(form.quantity);
  if (shouldCheck('quantity') && (!/^[1-9]\d*$/.test(form.quantity) || quantity > MAX_QUANTITY)) {
    errors.quantity = `数量仅支持 1 至 ${MAX_QUANTITY.toLocaleString()} 的正整数。`;
  }
  const penaltyAmount = Number(form.penaltyAmount);
  if (shouldCheck('penaltyAmount') && (!/^(0|[1-9]\d*)$/.test(form.penaltyAmount) || penaltyAmount > MAX_PENALTY_AMOUNT)) {
    errors.penaltyAmount = `最终处罚金额仅支持 0 至 ${MAX_PENALTY_AMOUNT.toLocaleString()} 元的整数。`;
  }
  if (shouldCheck('fact') && !form.fact.trim()) errors.fact = '请填写事实经过。';
  else if (shouldCheck('fact') && form.fact.trim().length > MAX_FACT_LENGTH) errors.fact = `事实经过最多 ${MAX_FACT_LENGTH} 字，避免模板正文溢出。`;
  if (shouldCheck('fact') && rule && pricing && pricing.unitPrice !== null) {
    const noticeText = buildNoticeSummary(form, rule, pricing, penaltyAmount);
    if (noticeText.length > MAX_NOTICE_SUMMARY_LENGTH) errors.fact = `按原考核单格式生成后超过 ${MAX_NOTICE_SUMMARY_LENGTH} 字，请压缩事实经过。`;
  }
  return errors;
}

export const hasErrors = (errors: FieldErrors) => Object.keys(errors).length > 0;
