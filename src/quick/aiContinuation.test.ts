import { describe, expect, it } from 'vitest';
import { continuationRequest } from './aiContinuation';

describe('本地条件补充不重新付费', () => {
  it('只提交继续凭证和条件，不追加描述重跑AI', () => {
    expect(continuationRequest('signed', { unloading_completed: true })).toEqual({ path: '/ai/continue', body: { continuation_token: 'signed', answers: { unloading_completed: true } } });
  });
  it('缺少凭证、无效数量或未选择的条件不能提交', () => {
    expect(() => continuationRequest('', { unloading_completed: true })).toThrow();
    expect(() => continuationRequest('signed', { billing_quantity: 0 })).toThrow();
    expect(() => continuationRequest('signed', { billing_quantity: 1.5 })).toThrow();
    expect(() => continuationRequest('signed', {})).toThrow();
  });
});
