import type { AssessmentRule } from '../types';

let cachedRules: AssessmentRule[] | null = null;
export async function loadRules(): Promise<AssessmentRule[]> {
  if (cachedRules) return cachedRules;
  const response = await fetch('/production-quality-rules.json');
  if (!response.ok) throw new Error('制度规则文件加载失败，请刷新后重试。');
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== 'object' || !Array.isArray((payload as Record<string, unknown>).rules)) throw new Error('制度规则文件格式异常，请重新生成。');
  const rules = (payload as { rules: AssessmentRule[] }).rules;
  if (!rules.length) throw new Error('制度规则文件为空，请检查源文档。');
  for (const rule of rules) {
    if (!rule.id || !rule.stage || !rule.clause || !Array.isArray(rule.pricingOptions)) throw new Error('制度规则文件包含无效条目，请重新生成。');
  }
  cachedRules = rules;
  return cachedRules;
}
