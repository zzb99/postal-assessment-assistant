import type { ReactNode } from 'react';
import type { Assessment } from '../api';
import { formatMoney } from '../utils/money';

const statusName = (status: string) => ({ draft: '草稿', effective: '正式', voided: '已作废' }[status] || status);

export function RecordTable({ rows, actions }: { rows: Assessment[]; actions?: (item: Assessment) => ReactNode }) {
  if (!rows.length) return <p className="empty">暂无记录。</p>;
  return <div className="table-wrap record-table"><table>
    <caption className="sr-only">考核记录列表</caption>
    <thead><tr><th scope="col">考核编号</th><th scope="col">发生日期</th><th scope="col">班次</th><th scope="col">被考核单位</th><th scope="col">问题类型</th><th scope="col">检查人</th><th scope="col">处罚金额</th><th scope="col">状态</th>{actions && <th scope="col">操作</th>}</tr></thead>
    <tbody>{rows.map((item) => <tr key={item.id}>
      <td data-label="考核编号">{item.assessment_no || `草稿 #${item.id}`}</td>
      <td data-label="发生日期">{item.incident_date}</td>
      <td data-label="班次">{item.shift}</td>
      <td data-label="被考核单位">{item.assessment_unit_name_snapshot}</td>
      <td data-label="问题类型" className="record-secondary">{item.category_name_snapshot || '—'}</td>
      <td data-label="检查人">{item.team} · {item.inspector_name}</td>
      <td data-label="处罚金额">¥ {formatMoney(item.penalty_amount)}</td>
      <td data-label="状态"><b className={`status ${item.status}`}>{statusName(item.status)}</b></td>
      {actions && <td data-label="操作" className="row-actions">{actions(item)}</td>}
    </tr>)}</tbody>
  </table></div>;
}
