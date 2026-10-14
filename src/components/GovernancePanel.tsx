import { useEffect, useRef, useState } from 'react';
import { api } from '../api';

type Device = { id: number; code: string; team: string; name: string; status: string };
type Policy = { version: string; effective_date: string; digest: string; approval_status: string; notice: string };
export function GovernancePanel() {
  const [devices, setDevices] = useState<Device[]>([]); const [policy, setPolicy] = useState<Policy | null>(null);
  const [error, setError] = useState(''); const [pending, setPending] = useState(false); const alive = useRef(true); const running = useRef(false);
  const sequence = useRef(0);
  async function refresh(signal?: AbortSignal) {
    const current = ++sequence.current;
    const [items, state] = await Promise.all([api<Device[]>('/governance/devices', { signal }), api<Policy>('/governance/policy', { signal })]);
    if (alive.current && current === sequence.current) { setDevices(items); setPolicy(state); }
  }
  useEffect(() => { alive.current = true; const controller = new AbortController(); void refresh(controller.signal).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); }); return () => { alive.current = false; controller.abort(); }; }, []);
  async function change(path: string, body: object) {
    if (running.current) return; running.current = true; ++sequence.current; setPending(true); setError('');
    try { await api(path, { method: path.endsWith('/approve') ? 'POST' : 'PUT', body: JSON.stringify(body) }); await refresh(); }
    catch (e) { if (alive.current) setError(e instanceof Error ? e.message : '授权失败'); }
    finally { running.current = false; if (alive.current) setPending(false); }
  }
  return <section className="card"><h2>设备登记（仅历史兼容）与制度状态</h2>{error && <p role="alert">{error}</p>}
    {policy && <><p>制度：{policy.version} · 生效：{policy.effective_date} · {policy.approval_status === 'published' ? '已直接发布' : policy.approval_status === 'approved' ? '旧版已核准' : '旧版内置目录'}</p><p>{policy.notice}</p>
      </>}
    <p>通过手机端登记码核实本人和设备后授权。换姓名/班组需要重新核准；无需职工每次登录。</p>
    <div className="actions"><button disabled={pending} onClick={() => void refresh().catch((e: Error) => setError(e.message))}>刷新登记</button></div>
    {devices.map((device) => <div key={device.id} className="quick-more"><p>{device.team} · {device.name} · 登记码 {device.code} · {device.status === 'approved' ? '已授权' : device.status === 'revoked' ? '已撤销' : '待授权'}</p><button disabled={pending} onClick={() => void change(`/governance/devices/${device.id}`, { approved: device.status !== 'approved', code: device.code })}>{device.status === 'approved' ? '撤销授权' : '核实后授权'}</button></div>)}
  </section>;
}
