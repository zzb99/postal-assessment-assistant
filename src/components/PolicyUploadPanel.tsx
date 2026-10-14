import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api, download } from '../api';

type Version = { id: string; version: string; effective_date: string; published_at: string; rule_count: number; sha256: string; current: boolean };
type Versions = { current: string; versions: Version[] };
export function PolicyUploadPanel() {
  const [list, setList] = useState<Versions | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [version, setVersion] = useState('');
  const [date, setDate] = useState(new Date().toLocaleDateString('en-CA'));
  const [busy, setBusy] = useState(false);
  const [major, setMajor] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function refresh() { setList(await api<Versions>('/policies/versions')); }
  useEffect(() => { void refresh().catch((e: Error) => setError(e.message)); }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !file || !version.trim() || !date) return;
    if (!window.confirm(`确认使用新制度 ${version}（生效日期 ${date}）？系统将直接发布，不需要第二人审批；新条款的金额不会未经核实自动处罚。`)) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const body = new FormData(); body.append('file', file); body.append('version', version.trim()); body.append('effective_date', date); body.append('allow_major_change', String(major));
      const result = await api<{ notice: string; rule_count: number }>('/policies/publish', { method: 'POST', body });
      setNotice(`${result.notice}，解析了 ${result.rule_count} 条记录。`);
      setFile(null); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : '上传失败'); }
    finally { setBusy(false); }
  }
  async function restore(id: string, label: string) {
    if (!window.confirm(`确认恢复 ${label} 为当前制度？这是主管/管理员直接操作，不需要第二人审批。`)) return;
    setBusy(true); setError(''); setNotice('');
    try { const result = await api<{ notice: string }>(`/policies/${id}/restore`, { method: 'POST' }); setNotice(result.notice); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : '恢复失败'); }
    finally { setBusy(false); }
  }
  return <section className="card"><h2>考核通则 Word 更换</h2>
    <p>主管和系统管理员可以直接上传并发布，不需要额外审批。历史制度与已生成文书会保留。复杂金额必须按原文人工核定。</p>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <form className="form compact-form" onSubmit={(e) => void submit(e)}>
      <label>新版制度 Word（仅 DOCX，最多5MB）<input type="file" accept=".docx" required onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
      <label>制度版本号<input required value={version} maxLength={64} onChange={(e) => setVersion(e.target.value)} placeholder="例如 20261020" /></label>
      <label>生效日期<input required type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
      <label><input type="checkbox" checked={major} onChange={(e) => setMajor(e.target.checked)} />确认这是条款数量大幅减少的完整修订版（非必要不要勾选）</label>
      <button className="primary" disabled={busy || !file || !version.trim()}>{busy ? '处理中…' : '上传并直接发布'}</button>
    </form>
    <h3>制度历史版本</h3><p>当前生效：{list?.current || '原始内置制度'}</p>
    {list?.versions.map((item) => <div key={item.id} className="quick-more">
      <p><strong>{item.version}{item.current ? '（当前）' : ''}</strong> · 生效 {item.effective_date} · {item.rule_count} 条 · 发布 {item.published_at.slice(0, 10)}</p>
      <div className="actions"><button type="button" disabled={busy} onClick={() => void download(`/policies/${item.id}/original`, `${item.version}.docx`).catch((e: Error) => setError(e.message))}>下载原件</button>
      {!item.current && <button type="button" disabled={busy} onClick={() => void restore(item.id, item.version)}>恢复此版本</button>}</div>
    </div>)}
  </section>;
}
