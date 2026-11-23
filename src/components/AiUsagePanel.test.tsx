import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AiUsagePanel, usageCost } from './AiUsagePanel';

describe('AI费用统计', () => {
  it('未知费用不能显示成零元', () => {
    expect(usageCost(null)).toBe('未知');
    expect(usageCost('0')).toBe('¥0.000000');
    expect(usageCost('0.0012')).toBe('¥0.001200');
  });
  it('后台面板不把估算说成真实账单', () => {
    const html = renderToStaticMarkup(<AiUsagePanel />);
    expect(html).toContain('AI用量与预估费用');
    expect(html).toContain('实际账单以DeepSeek为准');
  });
});
