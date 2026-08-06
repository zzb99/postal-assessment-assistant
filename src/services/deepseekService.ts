import type { AssessmentRule } from '../types';

export type AiAssessment = { ruleId: string; pricingId: string; quantity: string; confidence: 'high' | 'medium' | 'low'; reason: string; needsSupervisorReview: boolean };
export type AiPolicyAnswer = { ruleIds: string[]; conclusion: string; recommendedAction: string; consequence: string; needsSupervisorReview: boolean };
const endpoint = 'https://api.deepseek.com/chat/completions';

export function parseAiAssessment(raw: unknown): AiAssessment {
  if (!raw || typeof raw !== 'object') throw new Error('AI 返回数据为空，请重试。');
  const value = raw as Record<string, unknown>;
  for (const key of ['ruleId', 'pricingId', 'quantity', 'confidence', 'reason', 'needsSupervisorReview']) {
    if (!(key in value)) throw new Error(`AI 返回缺少必要字段：${key}，请重试。`);
  }
  if (typeof value.ruleId !== 'string' || typeof value.pricingId !== 'string') throw new Error('AI 返回的规则 ID 格式异常。');
  if (typeof value.quantity !== 'string' || typeof value.reason !== 'string') throw new Error('AI 返回的数量或理由格式异常。');
  if (typeof value.needsSupervisorReview !== 'boolean') throw new Error('AI 返回的主管认定标记异常。');
  if (!['high', 'medium', 'low'].includes(String(value.confidence))) throw new Error('AI 返回的置信度异常。');
  return value as AiAssessment;
}

export function parseAiPolicyAnswer(raw: unknown): AiPolicyAnswer {
  if (!raw || typeof raw !== 'object') throw new Error('AI 返回数据为空，请重试。');
  const value = raw as Record<string, unknown>;
  for (const key of ['ruleIds', 'conclusion', 'recommendedAction', 'consequence', 'needsSupervisorReview']) {
    if (!(key in value)) throw new Error(`AI 返回缺少必要字段：${key}，请重试。`);
  }
  if (!Array.isArray(value.ruleIds) || !value.ruleIds.every((id) => typeof id === 'string')) throw new Error('AI 返回的制度条款格式异常。');
  if (typeof value.conclusion !== 'string' || typeof value.recommendedAction !== 'string' || typeof value.consequence !== 'string' || typeof value.needsSupervisorReview !== 'boolean') throw new Error('AI 返回的制度问答格式异常。');
  return value as AiPolicyAnswer;
}

function questionCandidates(question: string, rules: AssessmentRule[]) {
  const source = question.replace(/\s/g, '');
  const grams = Array.from(new Set(Array.from(source).filter((char) => /[\u4e00-\u9fff]/.test(char))));
  return rules.map((rule) => {
    const searchable = `${rule.stage}${rule.name}${rule.original}${rule.keywords.join('')}`;
    const exactKeyword = rule.keywords.some((keyword) => keyword.length > 1 && source.includes(keyword));
    const overlap = grams.reduce((sum, char) => sum + (searchable.includes(char) ? 1 : 0), 0);
    return { rule, score: overlap + (exactKeyword ? 20 : 0) + (source.includes(rule.name) ? 30 : 0) };
  }).filter((item) => item.score > 1).sort((a, b) => b.score - a.score).slice(0, 12).map((item) => item.rule);
}

export async function askPolicyWithDeepSeek(apiKey: string, question: string, rules: AssessmentRule[]): Promise<AiPolicyAnswer> {
  if (!apiKey.trim()) throw new Error('未配置 DeepSeek API Key。');
  const candidates = questionCandidates(question, rules);
  if (!candidates.length) return { ruleIds: [], conclusion: '未找到可确认的制度依据。', recommendedAction: '请补充作业环节、发生行为或邮件处理情况后再问，或请主管认定。', consequence: '未匹配到条款时不输出处罚结论。', needsSupervisorReview: true };
  const ruleCatalog = candidates.map((rule) => ({ id: rule.id, stage: rule.stage, clause: rule.clause, name: rule.name, original: rule.original, pricingOptions: rule.pricingOptions, applicableConditions: rule.applicableConditions, followUpResponsibility: rule.followUpResponsibility, needsSupervisorReview: rule.needsSupervisorReview }));
  const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey.trim()}` }, body: JSON.stringify({ model: 'deepseek-chat', temperature: 0.1, response_format: { type: 'json_object' }, messages: [{ role: 'system', content: '你是邮政生产质量制度问答助手。员工会用日常口语提问。只能依据给定候选条款回答，不得编造条款、后果、金额或处罚。请返回 JSON：ruleIds（最多3个候选条款ID；无法确认则空数组）、conclusion（直白结论）、recommendedAction（应该怎么做）、consequence（制度规定的后果或考核标准；不明确时说明需主管认定）、needsSupervisorReview（布尔）。若无明确依据，ruleIds 必须为空且不得给出处罚结论。' }, { role: 'user', content: `员工问题：${question}\n\n候选正式制度条款：${JSON.stringify(ruleCatalog)}` }] }) });
  if (response.status === 402) throw new Error('DeepSeek 账户余额不足（402），请充值后重试。');
  if (!response.ok) throw new Error(`DeepSeek 请求失败（${response.status}），请检查密钥和网络后重试。`);
  const payload = await response.json() as { choices?: Array<{ message?: { content?: string } }> }; const content = payload.choices?.[0]?.message?.content;
  if (!content) throw new Error('DeepSeek 未返回制度问答结果。');
  const answer = parseAiPolicyAnswer(JSON.parse(content));
  return { ...answer, ruleIds: answer.ruleIds.filter((id) => candidates.some((rule) => rule.id === id)).slice(0, 3) };
}

export async function analyseWithDeepSeek(apiKey: string, fact: string, rules: AssessmentRule[]): Promise<AiAssessment> {
  if (!apiKey.trim()) throw new Error('请先填写 DeepSeek API Key；密钥只保存在当前浏览器。');
  const ruleCatalog = rules.map((rule) => ({ id: rule.id, stage: rule.stage, clause: rule.clause, name: rule.name, pricingOptions: rule.pricingOptions.map((item) => ({ id: item.id, unit: item.unit, unitPrice: item.unitPrice, condition: item.condition })) }));
  const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey.trim()}` }, body: JSON.stringify({ model: 'deepseek-chat', temperature: 0.1, response_format: { type: 'json_object' }, messages: [{ role: 'system', content: '你是邮政生产质量考核辅助工具。只能从提供的规则目录匹配，不得编造规则或金额。根据事实经过返回 JSON：ruleId、pricingId、quantity（正整数字符串，无法确认则""）、confidence（high/medium/low）、reason、needsSupervisorReview。规则不明确、数量不明确、金额含条件时必须 needsSupervisorReview=true。' }, { role: 'user', content: `事实经过：${fact}\n\n正式制度规则目录：${JSON.stringify(ruleCatalog)}` }] }) });
  if (response.status === 402) throw new Error('DeepSeek 账户余额不足（402），请登录开放平台查看余额或充值后重试。');
  if (!response.ok) throw new Error(`DeepSeek 请求失败（${response.status}），请检查密钥和网络后重试。`);
  const payload = await response.json() as { choices?: Array<{ message?: { content?: string } }> }; const content = payload.choices?.[0]?.message?.content;
  if (!content) throw new Error('DeepSeek 未返回可用分析结果。');
  try { return parseAiAssessment(JSON.parse(content)); } catch (error) { throw error instanceof Error ? error : new Error('DeepSeek 返回格式异常，请重试。'); }
}
