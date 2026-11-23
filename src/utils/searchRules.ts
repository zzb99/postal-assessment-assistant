import type { AssessmentRule } from '../types';

export function searchRules(rules: AssessmentRule[], query: string): AssessmentRule[] {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return rules;
  return rules.filter((rule) => {
    const text = [rule.stage, rule.clause, rule.name, rule.original, ...rule.keywords].join(' ').toLocaleLowerCase();
    return terms.every((term) => text.includes(term));
  });
}
