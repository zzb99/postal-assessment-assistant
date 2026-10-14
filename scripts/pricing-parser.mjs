import { createHash } from 'node:crypto';

const TYPES = new Set(['fixed', 'per_piece', 'per_bag', 'per_event', 'per_vehicle', 'per_hour', 'range', 'conditional', 'manual']);
const UNIT_TYPES = { 件: 'per_piece', 袋件: 'per_piece', 袋: 'per_bag', 次: 'per_event', 人次: 'per_event', 车次: 'per_vehicle', 小时: 'per_hour' };
const UNIT = '袋[（(]件[）)]|袋件|袋/件|人[·・]?次|车次|台次|班次|趟次|小时|件|袋|次|车|根|条|人|吨';
const normalizeUnit = (unit) => unit.replace(/袋[（(]件[）)]|袋\/件/g, '袋件').replace(/人[·・]次/g, '人次');

/** Classify every price, but never infer approval from an automatically parsed sentence. */
export function parsePricingOptions(text) {
  const options = [];
  const fees = [...text.matchAll(/(\d+(?:\.\d+)?)\s*(?:[-—至]\s*(\d+(?:\.\d+)?)\s*)?元/g)];
  for (const [index, fee] of fees.entries()) {
    const before = text.slice(Math.max(0, fee.index - 70), fee.index);
    const after = text.slice(fee.index + fee[0].length, fee.index + fee[0].length + 20);
    const suffix = after.match(new RegExp(`^\s*[/／]\s*(${UNIT})`));
    const prefix = [...before.matchAll(new RegExp(`每\s*(${UNIT})`, 'g'))].at(-1);
    const unit = suffix || prefix ? normalizeUnit((suffix || prefix)[1]) : '事项';
    const complex = /翻倍|加倍|比例|[%％]|上级|当年|达标|视情|另行|按照甲方|就高执行|以上|以下/.test(text) || fees.length > 1;
    const billingType = fee[2] ? 'range' : complex ? 'conditional' : unit === '事项' ? 'fixed' : (UNIT_TYPES[unit] || 'manual');
    options.push({ id: `p${index + 1}`, unit: fee[2] ? '待核定' : unit, unitPrice: fee[2] ? null : Number(fee[1]),
      condition: `原文计费标准：${fee[0]}；未经核准不得自动核算。`, billingType, autoApproved: false,
      requiredConditions: [], needsSupervisorReview: true });
  }
  return options.length ? options : [{ id: 'supervisor', unit: '待核定', unitPrice: null,
    condition: '原文未给出可直接自动计算的单一计价标准，请按原文手动核定。', billingType: /[%％]|翻倍|加倍|比例/.test(text) ? 'conditional' : 'manual',
    autoApproved: false, requiredConditions: [], needsSupervisorReview: true }];
}

/** Reviewed overrides are immutable pins: builds fail instead of silently dropping them. */
export function applyPricingOverrides(rules, document) {
  const copies = rules.map((rule) => ({ ...rule, pricingOptions: rule.pricingOptions.map((option) => ({ ...option })) }));
  const seen = new Set();
  for (const override of document.overrides || []) {
    if (seen.has(override.ruleId)) throw new Error(`Duplicate pricing override: ${override.ruleId}`);
    seen.add(override.ruleId);
    const rule = copies.find((item) => item.id === override.ruleId);
    if (!rule || rule.version !== override.version || createHash('sha256').update(rule.original, 'utf8').digest('hex') !== override.originalSha256) {
      throw new Error(`Pricing override source/version mismatch: ${override.ruleId}`);
    }
    for (const option of override.pricingOptions) {
      if (!TYPES.has(option.billingType) || typeof option.autoApproved !== 'boolean' || !Array.isArray(option.requiredConditions)) throw new Error(`Invalid pricing override: ${override.ruleId}`);
      if (!rule.pricingOptions.some((existing) => existing.id === option.id)) throw new Error(`Pricing option disappeared: ${override.ruleId}/${option.id}`);
    }
    rule.pricingOptions = override.pricingOptions.map((option) => ({ ...option }));
    rule.needsSupervisorReview = rule.pricingOptions.some((option) => option.needsSupervisorReview);
    rule.pricingOverride = { version: override.version, originalSha256: override.originalSha256 };
  }
  return copies;
}
