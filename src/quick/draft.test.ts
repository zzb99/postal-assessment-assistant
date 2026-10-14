import { beforeEach, describe, expect, it } from 'vitest';
import { readDraft, saveDraft, clearDraft, saveSessionProposal, readSessionProposal } from './draft';

describe('unfinished local draft', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
      getItem: (k: string) => values.get(k) ?? null,
      setItem: (k: string, v: string) => values.set(k, v), removeItem: (k: string) => values.delete(k),
    } });
    const session = new Map<string, string>();
    Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: {
      getItem: (k: string) => session.get(k) ?? null, setItem: (k: string, v: string) => session.set(k, v), removeItem: (k: string) => session.delete(k),
    } });
  });
  it('restores facts and text but never restores a formal signature', () => {
    saveDraft({ facts: '携带打火机', assessment_content: '正文草稿', ai_proposal: 'must-not-persist', quantity: '1', penalty_amount: '40' });
    expect(readDraft()).toMatchObject({ facts: '携带打火机', assessment_content: '正文草稿' });
    expect(readDraft()).not.toHaveProperty('ai_proposal');
    clearDraft(); expect(readDraft()).toEqual({});
  });
  it('restores a same-tab proposal only for the same device, identity and facts', () => {
    const draft = { incident_date: '2026-10-14', shift: '白班', unit: '1', facts: '检查事实', quantity: '1', penalty_amount: '40', team: '二班', inspector_name: '张三', ai_proposal: 'synthetic-signature' };
    saveSessionProposal(draft, '已核定正文');
    expect(readSessionProposal(draft)?.token).toBe('synthetic-signature');
    expect(readSessionProposal({ ...draft, inspector_name: '李四' })).toBeNull();
    expect(readSessionProposal({ ...draft, facts: '另一事实' })).toBeNull();
    localStorage.setItem('assessment-quick-device', 'a'.repeat(64));
    expect(readSessionProposal(draft)).toBeNull();
  });
});
