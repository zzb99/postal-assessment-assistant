import { describe, expect, it } from 'vitest';
import { amountInChinese, formatDate } from './currency';

describe('amountInChinese', () => {
  it('handles invalid and common whole-number amounts', () => {
    expect(amountInChinese(0)).toBe('零元整');
    expect(amountInChinese(-1)).toBe('零元整');
    expect(amountInChinese(5)).toBe('伍元整');
    expect(amountInChinese(10)).toBe('壹拾元整');
    expect(amountInChinese(100)).toBe('壹佰元整');
    expect(amountInChinese(10005)).toBe('壹万零伍元整');
  });
});

describe('formatDate', () => {
  it('formats an ISO date and rejects an empty value', () => {
    expect(formatDate('2026-08-06')).toBe('2026年8月6日');
    expect(formatDate('')).toBe('');
  });
});
