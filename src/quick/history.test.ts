import { describe, expect, it } from 'vitest';
import type { Assessment } from '../api';
import { mergeRecent } from './history';

describe('迟到的历史请求不能覆盖新生成单据', () => {
  it('合并去重，保留更新的版本并按ID排序', () => {
    const row = (id: number, updated_at: string) => ({ id, updated_at } as Assessment);
    const merged = mergeRecent([row(2, '2026-10-13T10:00:00Z'), row(1, '2026-10-13T10:00:00Z')], [row(1, '2026-10-13T09:00:00Z')]);
    expect(merged.map((value) => value.id)).toEqual([2, 1]);
    expect(merged[1].updated_at).toBe('2026-10-13T10:00:00Z');
    expect(mergeRecent([], Array.from({ length: 15 }, (_, id) => row(id, '2026-10-13T10:00:00Z')))).toHaveLength(10);
  });
});
