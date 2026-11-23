import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { FillController } from '@shared/controller';
import type { KeyValueStore, QuickApi } from '@shared/types';
import EmployeeApp, { parseRoute } from './EmployeeApp';
import { FillPage } from './FillPage';
import { isManagement } from '../Portal';

function memory(initial: Record<string, unknown> = {}): KeyValueStore {
  const data: Record<string, unknown> = { ...initial };
  return { get: (key) => data[key] ?? null, set: (key, value) => { data[key] = value; return true; }, remove: (key) => { delete data[key]; } };
}

const api = {} as QuickApi;

describe('employee web routes', () => {
  it('parses hash routes and keeps the admin website separate', () => {
    expect(parseRoute('#/result/12?fresh')).toEqual({ name: 'result', id: 12, fresh: true });
    expect(parseRoute('#/result/12')).toEqual({ name: 'result', id: 12, fresh: false });
    expect(parseRoute('#/records')).toEqual({ name: 'records' });
    expect(parseRoute('')).toEqual({ name: 'fill' });
    expect(isManagement({ pathname: '/', hash: '#manage' })).toBe(true);
    expect(isManagement({ pathname: '/admin', hash: '' })).toBe(true);
    expect(isManagement({ pathname: '/admin/', hash: '' })).toBe(true);
    expect(isManagement({ pathname: '/administrator', hash: '' })).toBe(false);
    expect(isManagement({ pathname: '/', hash: '#/records' })).toBe(false);
  });
});

describe('employee web rendering', () => {
  it('opens straight into the no-login fill form', () => {
    const html = renderToStaticMarkup(<EmployeeApp />);
    for (const text of ['填写考核单', '我的记录', '检查人', '检查信息', '描述现场问题', '生成考核单', '后台管理']) expect(html).toContain(text);
    for (const text of ['登录', '设备登记', '出单授权', '主管审批']) expect(html).not.toContain(text);
  });

  it('shows the review section with a confirmation for manual entry', () => {
    const controller = new FillController({
      api, store: memory({ 'assessment-quick-unfinished-v1': { mode: 'manual', assessment_content: '手工正文，考核100元。', quantity: '1', penalty_amount: '100' } }),
      sessionStore: memory(), deviceToken: 'a'.repeat(64), randomUuid: vi.fn(),
    });
    const html = renderToStaticMarkup(<FillPage controller={controller} />);
    expect(html).toContain('核对考核单');
    expect(html).toContain('考核正文 · 手动填写');
    expect(html).toContain('壹佰元整');
    expect(html).toContain('正文、制度依据和金额已核对。');
    expect(html).not.toContain('AI 智能整理');
    // 生成按钮不能是表单提交按钮，避免回车误生成正式单据。
    expect(html).not.toContain('type="submit"');
  });
});
