import type { QuickRecord } from '../src/shared/types';

export const record = (overrides: Partial<QuickRecord> = {}): QuickRecord => ({
  id: 7, assessment_no: 'KH-202611-0007', incident_date: '2026-11-23', shift: '白班', team: '二班', assessment_unit_id: 1,
  assessment_unit_name_snapshot: '华洋公司', inspector_name: '张三', quantity: 1, assessment_content: '现场吸烟。',
  penalty_amount: '500', penalty_amount_cn: '伍佰元整', status: 'effective', created_at: '2026-11-23T01:00:00Z',
  updated_at: '2026-11-23T01:00:00Z', finalized_at: '2026-11-23T01:00:01Z', voided_at: null, void_reason: null, ...overrides,
});
