import type { AssessmentRule } from '../types';
import { api } from '../api';

export async function loadRules(): Promise<AssessmentRule[]> {
  const payload: unknown = await api('/governance/rules');
  if (!payload || typeof payload !== 'object' || !Array.isArray((payload as Record<string, unknown>).rules)) throw new Error('制度规则文件格式异常，请重新生成。');
  const rules = (payload as { rules: AssessmentRule[] }).rules;
  if (!rules.length) throw new Error('制度规则文件为空，请检查源文档。');
  for (const rule of rules) {
    if (!rule.id || !rule.stage || !rule.clause || !Array.isArray(rule.pricingOptions)) throw new Error('制度规则文件包含无效条目，请重新生成。');
  }
  return rules;
}
