import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { Assessment } from '../api';
import { RecordTable } from './RecordTable';

describe('手机卡片台账与桌面表格共用记录', () => {
  it('保留字段标签，移动端无需横向滚动阅读', () => {
    const item = { id: 1, assessment_no: null, incident_date: '2026-10-09', shift: '白班', team: '一班', assessment_unit_name_snapshot: '华阳公司', category_name_snapshot: null, inspector_name: '吴正一', penalty_amount: '100.00', status: 'draft' } as Assessment;
    const html = renderToStaticMarkup(<RecordTable rows={[item]} actions={() => <button>继续填写</button>} />);
    expect(html).toContain('record-table');
    for (const label of ['考核编号', '发生日期', '被考核单位', '处罚金额', '状态', '操作']) expect(html).toContain(`data-label="${label}"`);
    expect(html).toContain('草稿 #1');
    expect(html).toContain('继续填写');
    expect(html.match(/华阳公司/g)).toHaveLength(1);
  });
  it('空记录有明确提示', () => {
    expect(renderToStaticMarkup(<RecordTable rows={[]} />)).toContain('暂无记录');
  });
});
