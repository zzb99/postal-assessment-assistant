import { describe, expect, it } from 'vitest';
import type { AssessmentRule } from '../types';
import { searchRules } from './searchRules';

const rules = [
  { id: '1', stage: '卸车', clause: '第14条', name: '破损拦截', original: '发现破损邮件未拦截', keywords: ['破袋'] },
  { id: '2', stage: '装车', clause: '第2条', name: '错发', original: '错发处理', keywords: [] },
] as AssessmentRule[];

describe('无AI密钥时仍可查正式制度', () => {
  it('支持环节、条款、原文、关键词检索', () => {
    for (const q of ['卸车', '第14条', '破损', '破袋', '  破损   拦截  ']) expect(searchRules(rules, q).map((v) => v.id)).toEqual(['1']);
    expect(searchRules(rules, '不匹配')).toEqual([]);
  });
  it('空词返回目录且不修改原始数组', () => {
    expect(searchRules(rules, ' ')).toEqual(rules);
    expect(rules).toHaveLength(2);
  });
});
