import { describe, expect, it } from 'vitest';
import { amountToChinese } from './money';

// Retain the useful former currency-wrapper cases against the implementation
// used by both the employee form and management console.
describe('current amount conversion', () => {
  it('formats whole amounts and rejects a negative amount', () => {
    expect(amountToChinese(0)).toBe('零元整');
    expect(amountToChinese(-1)).toBe('金额格式不正确');
    expect(amountToChinese(5)).toBe('伍元整');
    expect(amountToChinese(10)).toBe('壹拾元整');
    expect(amountToChinese(100)).toBe('壹佰元整');
    expect(amountToChinese(10005)).toBe('壹万零伍元整');
  });
});
