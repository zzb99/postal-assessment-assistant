import { useCallback, useEffect, useState } from 'react';
import { formatMoney, mergeRecent, statusLabel } from '@shared/format';
import type { QuickRecord } from '@shared/types';
import { loadRecords } from './platform';

/** 本机生成的考核单（按本机凭证查询，不按自填姓名查全员记录）。 */
export function RecordsPage() {
  const [items, setItems] = useState<QuickRecord[]>([]);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async (next: number) => {
    setLoading(true);
    setError('');
    try {
      const result = await loadRecords(next);
      setItems((old) => (next === 1 ? result.items : mergeRecent(old, result.items, 1000)));
      setPage(next);
      setTotal(result.total);
      setDone(result.items.length < result.page_size || next * result.page_size >= result.total);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '读取失败，请稍后重试。');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(1); }, [load]);

  return (
    <div className="emp-page">
      <div className="emp-hero">
        <h1>我的记录</h1>
        <p>本机生成的考核单{total ? `，共 ${total} 张` : ''}。换手机或清除浏览器数据后，旧记录请到后台查询。</p>
      </div>
      {error && <div className="emp-alert emp-alert-error" role="alert">{error}<button type="button" className="emp-link" onClick={() => void load(page || 1)}>重试</button></div>}
      {!items.length && !loading && !error && <p className="emp-empty">还没有考核单。<a href="#/">去填写第一张</a></p>}
      <ul className="emp-records">
        {items.map((item) => (
          <li key={item.id}>
            <a href={`#/result/${item.id}`}>
              <span className="emp-record-top"><strong>{item.assessment_no || `未生成 #${item.id}`}</strong><span className={`emp-status ${item.status}`}>{statusLabel(item.status)}</span></span>
              <span className="emp-record-unit"><span>{item.assessment_unit_name_snapshot}</span><strong>¥{formatMoney(item.penalty_amount)}</strong></span>
              <small>{item.incident_date} {item.shift} · {item.team} {item.inspector_name}</small>
            </a>
          </li>
        ))}
      </ul>
      {loading && <p className="emp-empty">正在读取…</p>}
      {!loading && items.length > 0 && (done ? <p className="emp-hint emp-center">已显示全部</p> : <button type="button" className="emp-btn emp-btn-block" onClick={() => void load(page + 1)}>加载更多</button>)}
    </div>
  );
}
