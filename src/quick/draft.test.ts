import { beforeEach, describe, expect, it } from 'vitest';
import { readDraft, saveDraft, clearDraft } from './draft';

describe('unfinished local draft', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
      getItem: (k: string) => values.get(k) ?? null,
      setItem: (k: string, v: string) => values.set(k, v), removeItem: (k: string) => values.delete(k),
    } });
  });
  it('restores facts and text but never restores a formal signature', () => {
    saveDraft({ facts: '携带打火机', assessment_content: '正文草稿', ai_proposal: 'must-not-persist', quantity: '1', penalty_amount: '40' });
    expect(readDraft()).toMatchObject({ facts: '携带打火机', assessment_content: '正文草稿' });
    expect(readDraft()).not.toHaveProperty('ai_proposal');
    clearDraft(); expect(readDraft()).toEqual({});
  });
});
