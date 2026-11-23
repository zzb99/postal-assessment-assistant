import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import QuickPage from './QuickPage';

describe('quick generation recovery', () => {
  it('shows a direct writing workflow without registration or approval gates', () => {
    const html = renderToStaticMarkup(<QuickPage />);
    expect(html).toContain('生成考核单');
    expect(html).not.toContain('出单准备');
    expect(html).not.toContain('登记当前身份');
    expect(html).not.toContain('本机出单授权');
    expect(html).toContain('填写信息');
    expect(html).toContain('描述问题');
  });
});
