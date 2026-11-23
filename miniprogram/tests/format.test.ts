import { describe, expect, it } from 'vitest';
import { amountToChinese, beijingToday, documentFileName, formatCnDate, formatMoney, mergeRecent, shareText, statusLabel } from '../src/shared/format';
import { isDeviceToken, reuseRequestId, stableJson, toHex, uuidFromBytes } from '../src/shared/ids';
import { apiErrorMessage } from '../src/shared/errors';
import { record } from './fixtures';

describe('money and dates without Intl', () => {
  it.each([
    ['0', '零元整'], ['5', '伍元整'], ['10', '壹拾元整'], ['100', '壹佰元整'], ['500.00', '伍佰元整'],
    ['10005', '壹万零伍元整'], ['1234.5', '壹仟贰佰叁拾肆元伍角'], ['abc', '金额格式不正确'],
  ])('amountToChinese(%s)', (value, expected) => expect(amountToChinese(value)).toBe(expected));

  it('formats money with thousands separators', () => {
    expect(formatMoney('1234.5')).toBe('1,234.50');
    expect(formatMoney(1000000)).toBe('1,000,000.00');
    expect(formatMoney('x')).toBe('0.00');
  });

  it('uses Beijing time for today regardless of device timezone', () => {
    expect(beijingToday(Date.UTC(2026, 10, 23, 15, 59))).toBe('2026-11-23');
    expect(beijingToday(Date.UTC(2026, 10, 23, 16, 0))).toBe('2026-11-24');
    expect(formatCnDate('2026-01-05')).toBe('2026年1月5日');
  });
});

describe('record helpers', () => {
  it('builds safe file names and share text', () => {
    expect(documentFileName(record(), 'pdf')).toBe('KH-202611-0007.pdf');
    expect(documentFileName(record({ assessment_no: null }), 'word')).toBe('考核单-7.docx');
    expect(documentFileName(record({ assessment_no: 'A/B:C' }), 'png')).toBe('A-B-C.png');
    expect(shareText(record())).toContain('考核金额：500.00元（伍佰元整）');
    expect(statusLabel('voided')).toBe('已作废');
  });

  it('merges by id keeping the newest update', () => {
    const merged = mergeRecent([record({ id: 1, status: 'effective' })], [record({ id: 1, status: 'voided', updated_at: '2026-11-24T00:00:00Z' }), record({ id: 2 })]);
    expect(merged.map((item) => [item.id, item.status])).toEqual([[2, 'effective'], [1, 'voided']]);
  });
});

describe('identifiers', () => {
  it('validates device tokens and formats uuid v4', () => {
    expect(toHex([0, 15, 255])).toBe('000fff');
    expect(isDeviceToken('a'.repeat(64))).toBe(true);
    expect(isDeviceToken('A'.repeat(64))).toBe(false);
    const uuid = uuidFromBytes(new Array(16).fill(255));
    expect(uuid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(() => uuidFromBytes([1, 2])).toThrow();
  });

  it('reuses the request id for the same content even after re-signing', () => {
    expect(stableJson({ b: 1, a: [2, { d: 3, c: undefined }] })).toBe('{"a":[2,{"d":3}],"b":1}');
    const first = reuseRequestId({ penalty_amount: '500', ai_proposal: 'old' }, null, 'id-1');
    expect(reuseRequestId({ ai_proposal: 'new', penalty_amount: '500' }, first, 'id-2').requestId).toBe('id-1');
    expect(reuseRequestId({ penalty_amount: '600', ai_proposal: 'new' }, first, 'id-3').requestId).toBe('id-3');
  });
});

describe('error messages', () => {
  it('maps backend responses to readable Chinese', () => {
    expect(apiErrorMessage(422, { detail: '考核正文金额与填写金额不一致' }, 'x')).toBe('考核正文金额与填写金额不一致');
    expect(apiErrorMessage(422, { detail: [{ loc: ['body'] }] }, 'x')).toContain('正整数');
    expect(apiErrorMessage(401, { detail: '本机凭证无效' }, 'x')).toContain('重新打开');
    expect(apiErrorMessage(502, null, 'x')).toContain('服务暂时不可用');
    expect(apiErrorMessage(418, null, '兜底')).toBe('兜底');
  });
});
