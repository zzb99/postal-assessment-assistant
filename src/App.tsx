import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowLeftOnRectangleIcon, ChartBarIcon, ClipboardDocumentListIcon, DocumentPlusIcon, HomeIcon, MagnifyingGlassIcon, ShieldCheckIcon } from '@heroicons/react/24/outline';
import { api, clearToken, download, getToken, loadBlobUrl, setToken } from './api';
import type { AiAssessmentResult, AiPolicyResult, Assessment, AssessmentPage, CurrentUser, GroupStatistic, ManagedUser, ManagementCatalog, Overview, ReferenceData } from './api';
import { amountToChinese, formatMoney } from './utils/money';
import { getPermissions, navigationFor, roleName } from './permissions';
import type { Page } from './permissions';
import { RecordTable } from './components/RecordTable';
import { AiUsagePanel } from './components/AiUsagePanel';
import { PolicyUploadPanel } from './components/PolicyUploadPanel';
import { loadRules } from './data/rules';
import { searchRules } from './utils/searchRules';
import { createRequestGate } from './utils/requestGate';
import type { AssessmentRule } from './types';
import './app.css';

type Notice = { type: 'success' | 'error'; text: string } | null;
type FormData = { incident_date: string; shift: string; team: string; assessment_unit_id: string; assessment_unit_name: string; inspector_name: string; quantity: string; assessment_content: string; category_id: string; operation_stage: string; regulation_version: string; penalty_amount: string; remark: string };

const localDate = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date());
const emptyForm = (): FormData => ({ incident_date: localDate(), shift: '白班', team: '一班', assessment_unit_id: '', assessment_unit_name: '', inspector_name: '', quantity: '', assessment_content: '', category_id: '', operation_stage: '', regulation_version: '20260819', penalty_amount: '', remark: '' });
const statusName = (status: string) => ({ draft: '草稿', effective: '正式', voided: '已作废' }[status] || status);

function App() {
  const [user, setUser] = useState<CurrentUser | null>(null); const [reference, setReference] = useState<ReferenceData | null>(null);
  const [page, setPage] = useState<Page>('home'); const [notice, setNotice] = useState<Notice>(null); const [busy, setBusy] = useState(false);
  const [login, setLogin] = useState({ username: '', password: '' }); const [form, setForm] = useState<FormData>(emptyForm); const [draft, setDraft] = useState<Assessment | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null); const [ledger, setLedger] = useState<AssessmentPage>({ items: [], total: 0, page: 1, page_size: 20 });
  const [search, setSearch] = useState(''); const [status, setStatus] = useState(''); const [selected, setSelected] = useState<Assessment | null>(null);
  const [stats, setStats] = useState<{ units: GroupStatistic[]; departments: GroupStatistic[]; categories: GroupStatistic[] }>({ units: [], departments: [], categories: [] });
  const [aiEnabled, setAiEnabled] = useState(false);
  const [homeRecords, setHomeRecords] = useState<AssessmentPage>({ items: [], total: 0, page: 1, page_size: 20 });
  const sessionGate = useRef(createRequestGate()).current;
  const ledgerGate = useRef(createRequestGate()).current;
  const homeGate = useRef(createRequestGate()).current;
  const statsGate = useRef(createRequestGate()).current;
  const mutationBusy = useRef(false);
  const [formGeneration, setFormGeneration] = useState(0);
  const viewScope = sessionGate.capture();
  const say = (type: 'success' | 'error', text: string) => { if (sessionGate.isCurrent(viewScope)) setNotice({ type, text }); };
  const bootstrap = async () => {
    const scope = sessionGate.capture();
    const me = await api<CurrentUser>('/auth/me');
    if (!sessionGate.isCurrent(scope)) return;
    const [refs, records, ai, board] = await Promise.all([
      api<ReferenceData>('/management/reference-data'), api<AssessmentPage>('/assessments?page=1&page_size=20'),
      api<{ enabled: boolean }>('/ai/status'),
      me.role === 'employee' ? Promise.resolve(null) : api<Overview>('/statistics/overview'),
    ]);
    if (!sessionGate.isCurrent(scope)) return;
    setUser(me); setReference(refs); setLedger(records); setHomeRecords(records); setAiEnabled(ai.enabled); setOverview(board); setPage('home');
  };
  const loadLedger = async (nextPage = 1) => {
    const scope = sessionGate.capture(); const request = ledgerGate.invalidate();
    const q = new URLSearchParams({ page: String(nextPage), page_size: '20' });
    if (search.trim()) q.set('keyword', search.trim()); if (status) q.set('status', status);
    try { const records = await api<AssessmentPage>(`/assessments?${q}`); if (sessionGate.isCurrent(scope) && ledgerGate.isCurrent(request)) setLedger(records); }
    catch (error) { if (sessionGate.isCurrent(scope) && ledgerGate.isCurrent(request)) throw error; }
  };
  const loadHome = async () => {
    const scope = sessionGate.capture(); const request = homeGate.invalidate();
    try {
      const [records, board] = await Promise.all([api<AssessmentPage>('/assessments?page=1&page_size=20'), user?.role === 'employee' ? Promise.resolve(null) : api<Overview>('/statistics/overview')]);
      if (sessionGate.isCurrent(scope) && homeGate.isCurrent(request)) { setHomeRecords(records); setOverview(board); }
    } catch (error) { if (sessionGate.isCurrent(scope) && homeGate.isCurrent(request)) throw error; }
  };
  const loadStats = async () => {
    const scope = sessionGate.capture(); const request = statsGate.invalidate();
    try {
      const [units, departments, categories] = await Promise.all([api<GroupStatistic[]>('/statistics/units'), api<GroupStatistic[]>('/statistics/departments'), api<GroupStatistic[]>('/statistics/categories')]);
      if (sessionGate.isCurrent(scope) && statsGate.isCurrent(request)) setStats({ units, departments, categories });
    } catch (error) { if (sessionGate.isCurrent(scope) && statsGate.isCurrent(request)) throw error; }
  };
  useEffect(() => {
    const scope = sessionGate.capture();
    if (getToken()) void bootstrap().catch((error: Error) => { if (sessionGate.isCurrent(scope)) { clearToken(); setNotice({ type: 'error', text: error.message }); } });
    return () => { sessionGate.invalidate(); };
  }, []);
  const loginSubmit = async (event: FormEvent) => {
    event.preventDefault(); if (mutationBusy.current) return;
    const scope = sessionGate.invalidate(); mutationBusy.current = true; setBusy(true);
    try {
      const value = await api<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify(login) });
      if (!sessionGate.isCurrent(scope)) return;
      setToken(value.access_token); await bootstrap();
      if (sessionGate.isCurrent(scope)) { setLogin({ username: '', password: '' }); setNotice({ type: 'success', text: '登录成功。' }); }
    } catch (error) { if (sessionGate.isCurrent(scope)) { clearToken(); setNotice({ type: 'error', text: error instanceof Error ? error.message : '登录失败。' }); } }
    finally { if (sessionGate.isCurrent(scope)) { mutationBusy.current = false; setBusy(false); } }
  };
  const update = (key: keyof FormData, value: string) => setForm((old) => ({ ...old, [key]: value }));
  const input = () => ({ ...form, quantity: Number(form.quantity), assessment_unit_id: form.assessment_unit_id ? Number(form.assessment_unit_id) : null, category_id: form.category_id ? Number(form.category_id) : null });
  const persistDraft = async () => draft
    ? api<Assessment>(`/assessments/${draft.id}`, { method: 'PUT', body: JSON.stringify({ ...input(), updated_at: draft.updated_at }) })
    : api<Assessment>('/assessments', { method: 'POST', body: JSON.stringify(input()) });
  const mutate = async (operation: (valid: () => boolean) => Promise<void>) => {
    if (mutationBusy.current) return;
    const scope = sessionGate.capture(); const valid = () => sessionGate.isCurrent(scope);
    mutationBusy.current = true; setBusy(true);
    try { await operation(valid); } catch (error) { if (valid()) say('error', error instanceof Error ? error.message : '操作失败。'); }
    finally { if (valid()) { mutationBusy.current = false; setBusy(false); } }
  };
  const saveDraft = () => mutate(async (valid) => { const value = await persistDraft(); if (!valid()) return; setDraft(value); say('success', '草稿已保存，主管可查看并复核。'); await Promise.all([loadLedger(), loadHome()]); });
  const finalize = () => mutate(async (valid) => {
    if (!user || !getPermissions(user.role).finalize) return;
    const current = await persistDraft(); if (!valid()) return; setDraft(current);
    const value = await api<Assessment>(`/assessments/${current.id}/finalize`, { method: 'POST', body: JSON.stringify({ updated_at: current.updated_at }) });
    if (!valid()) return;
    setDraft(null); setForm(emptyForm()); setSelected(value); setPage('ledger'); say('success', `考核单 ${value.assessment_no} 已正式生成。`);
    await Promise.all([loadLedger(), loadHome()]);
  });
  const openDraft = (item: Assessment) => mutate(async (valid) => {
    const value = await api<Assessment>(`/assessments/${item.id}`); if (!valid()) return;
    if (value.status !== 'draft') throw new Error('该记录已不是草稿，请刷新台账。');
    fillDraft(value); setPage('create'); setNotice(null);
  });
  const fillDraft = (value: Assessment) => {
    setDraft(value); setForm({ incident_date: value.incident_date, shift: value.shift, team: value.team, assessment_unit_id: value.assessment_unit_id ? String(value.assessment_unit_id) : '', assessment_unit_name: value.assessment_unit_name_snapshot, inspector_name: value.inspector_name, quantity: String(value.quantity), assessment_content: value.assessment_content, category_id: value.category_id ? String(value.category_id) : '', operation_stage: value.operation_stage || '', regulation_version: value.regulation_version || '', penalty_amount: value.penalty_amount, remark: value.remark || '' });
  };
  const copy = (item: Assessment) => mutate(async (valid) => { const value = await api<Assessment>(`/assessments/${item.id}/copy`, { method: 'POST' }); if (!valid()) return; fillDraft(value); setPage('create'); say('success', '已复制为新草稿，原记录保持不变。'); });
  const voidItem = async (item: Assessment) => {
    const reason = window.prompt(`作废 ${item.assessment_no}，请填写原因：`); if (!reason?.trim()) return;
    await mutate(async (valid) => { const value = await api<Assessment>(`/assessments/${item.id}/void`, { method: 'POST', body: JSON.stringify({ reason }) }); if (!valid()) return; setSelected(value); say('success', '已作废，编号不会复用。'); await Promise.all([loadLedger(), loadHome(), loadStats()]); });
  };
  const moneyCn = useMemo(() => amountToChinese(form.penalty_amount), [form.penalty_amount]);
  useEffect(() => { window.scrollTo({ top: 0 }); }, [page, user?.id]);
  if (!user || !reference) return <Login login={login} setLogin={setLogin} submit={loginSubmit} busy={busy} notice={notice} />;
  const permissions = getPermissions(user.role);
  const employee = user.role === 'employee';
  const menus = navigationFor(user.role);
  const activePage = menus.some((item) => item.id === page) ? page : 'home';
  const icons = { home: HomeIcon, create: DocumentPlusIcon, ledger: ClipboardDocumentListIcon, policy: MagnifyingGlassIcon, statistics: ChartBarIcon, management: ShieldCheckIcon };
  const reset = () => { setFormGeneration((value) => value + 1); setDraft(null); setForm(emptyForm()); setNotice(null); };
  const navigate = (id: Page) => {
    if (mutationBusy.current) return; const scope = sessionGate.capture(); setPage(id);
    const operation = id === 'statistics' ? loadStats : id === 'home' ? loadHome : id === 'ledger' ? loadLedger : null;
    if (operation) void operation().catch((error: Error) => { if (sessionGate.isCurrent(scope)) say('error', error.message); });
  };
  const logout = () => { sessionGate.invalidate(); mutationBusy.current = false; setBusy(false); clearToken(); setUser(null); setReference(null); setPage('home'); setNotice(null); reset(); setSelected(null); setSearch(''); setStatus(''); setLedger({ items: [], total: 0, page: 1, page_size: 20 }); setHomeRecords({ items: [], total: 0, page: 1, page_size: 20 }); setOverview(null); setStats({ units: [], departments: [], categories: [] }); };
  return <div className={`office-app ${employee ? 'employee-app' : 'supervisor-app'}`}>
    <aside className="sidebar"><div className="brand"><span>邮</span><b>邮件处理中心<small>考核管理系统</small></b></div>
      <nav aria-label="功能导航">{menus.map(({ id, label }) => { const Icon = icons[id]; return <button disabled={busy} aria-current={activePage === id ? 'page' : undefined} aria-label={label} className={activePage === id ? 'active' : ''} key={id} onClick={() => navigate(id)}><Icon aria-hidden="true" /><span>{label}</span></button>; })}</nav>
      <p>{employee ? '本人填报 · 主管复核' : '正式数据统一存储'}<br />操作全程留痕</p>
    </aside>
    <div className="shell"><header><div><strong>{menus.find((item) => item.id === activePage)?.label}</strong><small>{employee ? '职工工作台' : '主管工作台'}</small></div><div className="user"><span>{user.display_name}</span><em>{roleName(user.role)}</em><button onClick={logout} aria-label="退出登录" title="退出登录"><ArrowLeftOnRectangleIcon /></button></div></header>
      {notice && <div role={notice.type === 'error' ? 'alert' : 'status'} className={`notice ${notice.type}`}>{notice.text}<button aria-label="关闭提示" onClick={() => setNotice(null)}>×</button></div>}
      <main>
        {activePage === 'home' && (employee ? <EmployeeHome user={user} rows={homeRecords.items} total={homeRecords.total} create={() => { if (!busy) { reset(); setPage('create'); } }} goLedger={() => navigate('ledger')} edit={openDraft} /> : <Home overview={overview} rows={homeRecords.items} goLedger={() => navigate('ledger')} />)}
        {activePage === 'create' && permissions.create && <Create key={`${draft?.id ?? 'new'}-${formGeneration}`} employee={employee} aiEnabled={aiEnabled} form={form} refData={reference} update={update} setUnit={(id) => { const unit = reference.units.find((item) => String(item.id) === id); setForm((old) => ({ ...old, assessment_unit_id: id, assessment_unit_name: unit?.name || '' })); }} moneyCn={moneyCn} draft={draft} busy={busy} save={saveDraft} finalize={finalize} reset={reset} />}
        {activePage === 'policy' && <><PolicyAssistant aiEnabled={aiEnabled} />{(user.role === 'admin' || user.role === 'department_manager') && <PolicyUploadPanel />}{user.role === 'admin' && <AiUsagePanel />}</>}
        {activePage === 'ledger' && <Ledger employee={employee} canCreate={permissions.create} canExport={permissions.export} edit={openDraft} data={ledger} search={search} setSearch={setSearch} status={status} setStatus={setStatus} load={loadLedger} selected={selected} setSelected={setSelected} copy={copy} voidItem={voidItem} canVoid={permissions.void} busy={busy} say={say} />}
        {activePage === 'statistics' && permissions.statistics && <Statistics overview={overview} stats={stats} />}
        {activePage === 'management' && permissions.manage && <Management refData={reference} refreshReference={async () => { if (!sessionGate.isCurrent(viewScope)) return; const refs = await api<ReferenceData>('/management/reference-data'); if (sessionGate.isCurrent(viewScope)) setReference(refs); }} say={say} />}
      </main>
    </div>
  </div>;
}

function Login({ login, setLogin, submit, busy, notice }: { login: { username: string; password: string }; setLogin: (next: { username: string; password: string }) => void; submit: (event: FormEvent) => void; busy: boolean; notice: Notice }) { return <div className="login"><form onSubmit={submit}><div className="brand"><span>邮</span><b>邮件处理中心<small>考核管理系统</small></b></div><h1>登录内部系统</h1><p>考核单、台账和统计均以服务器正式记录为准。</p>{notice?.type === 'error' && <div className="error">{notice.text}</div>}<label>用户名<input autoComplete="username" value={login.username} onChange={(e) => setLogin({ ...login, username: e.target.value })} /></label><label>密码<input type="password" autoComplete="current-password" value={login.password} onChange={(e) => setLogin({ ...login, password: e.target.value })} /></label><button className="primary" disabled={busy}>{busy ? '正在登录…' : '登录'}</button><small>首次部署由管理员通过环境变量初始化账号，系统不提供默认密码。</small></form></div>; }
function Home({ overview, rows, goLedger }: { overview: Overview | null; rows: Assessment[]; goLedger: () => void }) { const cards = [['本月考核次数', overview?.month_count || 0, '次'], ['本月处罚金额', formatMoney(overview?.month_amount || 0), '元'], ['本年度考核次数', overview?.year_count || 0, '次'], ['本年度处罚金额', formatMoney(overview?.year_amount || 0), '元'], ['涉及单位', overview?.unit_count || 0, '家']]; return <section><Intro kicker="数据总览" title="考核业务工作台" text="所有统计均由正式考核单实时汇总，作废记录默认不计入。" /><div className="metrics">{cards.map(([l, v, u]) => <article key={l}><span>{l}</span><strong>{v}<small>{u}</small></strong></article>)}</div><section className="panel"><div className="panel-head"><div><h2>最近考核记录</h2><p>台账、统计和后续 Excel 共用同一数据源。</p></div><button onClick={goLedger}>进入台账</button></div><RecordTable rows={rows.slice(0, 6)} /></section></section>; }
function EmployeeHome({ user, rows, total, create, goLedger, edit }: { user: CurrentUser; rows: Assessment[]; total: number; create: () => void; goLedger: () => void; edit: (item: Assessment) => Promise<void> }) {
  return <section><Intro kicker="职工工作台" title={`${user.display_name}，你好`} text="专注现场填报；草稿保存后由主管查看、复核并正式生成。" />
    <div className="quick-actions"><button className="primary" onClick={create}><DocumentPlusIcon aria-hidden="true" /><strong>新建现场填报</strong><span>填写事实，保存草稿</span></button><button onClick={goLedger}><ClipboardDocumentListIcon aria-hidden="true" /><strong>我的记录 · {total}</strong><span>仅显示本人创建的记录</span></button></div>
    <section className="panel"><div className="panel-head"><h2>最近填报</h2><button onClick={goLedger}>全部记录</button></div><RecordTable rows={rows.slice(0, 6)} actions={(item) => <button onClick={() => { if (item.status === 'draft') void edit(item); else goLedger(); }}>{item.status === 'draft' ? '继续填写' : '查看记录'}</button>} /></section>
  </section>;
}

function Create({ employee, aiEnabled, form, refData, update, setUnit, moneyCn, draft, busy, save, finalize, reset }: { employee: boolean; aiEnabled: boolean; form: FormData; refData: ReferenceData; update: (key: keyof FormData, value: string) => void; setUnit: (id: string) => void; moneyCn: string; draft: Assessment | null; busy: boolean; save: () => Promise<void>; finalize: () => Promise<void>; reset: () => void }) {
  const [facts, setFacts] = useState(''); const [aiBusy, setAiBusy] = useState(false); const [aiMessage, setAiMessage] = useState('');
  const aiGate = useRef(createRequestGate()).current;
  useEffect(() => { aiGate.invalidate(); setAiBusy(false); return () => { aiGate.invalidate(); }; }, [facts, form, aiGate]);
  const analyse = async () => {
    if (!aiEnabled || aiBusy || busy) return;
    const request = aiGate.invalidate(); setAiBusy(true); setAiMessage('');
    try {
      const result = await api<AiAssessmentResult>('/ai/assessment', { method: 'POST', body: JSON.stringify({ facts, incident_date: form.incident_date, shift: form.shift, assessment_unit_name: form.assessment_unit_name }) });
      if (!aiGate.isCurrent(request)) return;
      if (result.assessment_content && result.quantity && result.penalty_amount) { update('assessment_content', result.assessment_content); update('quantity', String(result.quantity)); update('penalty_amount', result.penalty_amount); }
      setAiMessage(`${result.needs_supervisor_review ? '需主管复核：' : '已按制度目录整理：'}${result.reason}`);
    } catch (error) { if (aiGate.isCurrent(request)) setAiMessage(error instanceof Error ? error.message : 'AI识别失败。'); }
    finally { if (aiGate.isCurrent(request)) setAiBusy(false); }
  };
  const classification = <div className="fields"><label>问题分类<select value={form.category_id} onChange={(e) => update('category_id', e.target.value)}><option value="">未分类</option>{refData.categories.map((v) => <option value={v.id} key={v.id}>{v.name}</option>)}</select></label><label>作业环节<select value={form.operation_stage} onChange={(e) => update('operation_stage', e.target.value)}><option value="">未填写</option>{refData.operation_stages.map((v) => <option key={v}>{v}</option>)}</select></label></div>;
  return <section>
    <div className="intro split"><div><p>{draft ? '草稿编辑' : employee ? '现场填报' : '新建考核单'}</p><h1>{draft ? `草稿 #${draft.id}` : employee ? '记录现场检查问题' : '开具通信生产考核通知单'}</h1><span>{employee ? '保存后主管可见；职工不能正式生成或作废。' : '先复核事实与金额，再生成同源Word和PDF。'}</span></div><button disabled={busy || aiBusy} onClick={reset}>新建空白{employee ? '填报' : '考核单'}</button></div>
    <div className={`form-layout ${employee ? 'simple-form' : ''}`}><form className="panel form" onSubmit={(e) => { e.preventDefault(); if (!aiBusy) void (employee ? save() : finalize()); }}><fieldset className="form-fields" disabled={busy}>
      <h2>1. 检查信息</h2><div className="fields">
        <label>发生日期<input type="date" required value={form.incident_date} onChange={(e) => update('incident_date', e.target.value)} /></label>
        <label>班次<select required value={form.shift} onChange={(e) => update('shift', e.target.value)}>{refData.shifts.map((v) => <option key={v}>{v}</option>)}</select></label>
        <label>班组<input required maxLength={32} value={form.team} onChange={(e) => update('team', e.target.value)} placeholder="自由填写班组" /></label>
        <label>检查人<input required maxLength={100} value={form.inspector_name} onChange={(e) => update('inspector_name', e.target.value)} placeholder="自由填写姓名" /></label>
        <label>被考核单位<select required value={form.assessment_unit_id} onChange={(e) => setUnit(e.target.value)}><option value="">请选择</option>{refData.units.map((v) => <option value={v.id} key={v.id}>{v.name}</option>)}</select></label>
      </div>
      <h2>2. 问题与金额</h2>
      <details className="optional-fields"><summary>AI辅助整理（可选）{!aiEnabled && ' · 暂未启用'}</summary>{aiEnabled ? <><label>现场事实<textarea maxLength={2000} value={facts} onChange={(e) => setFacts(e.target.value)} placeholder="填写事实、位置、数量和发现经过；AI结果必须人工确认。" /></label><button type="button" disabled={busy || aiBusy || facts.trim().length < 5 || !form.assessment_unit_name} onClick={() => void analyse()}>{aiBusy ? '正在识别…' : '按制度整理'}</button>{aiMessage && <p className="helper-message" role="status">{aiMessage}</p>}</> : <p className="helper-message">服务端尚未配置DeepSeek密钥，可直接手动填写下方考核事项，不影响保存草稿。</p>}</details>
      <label>考核事项<textarea required maxLength={600} value={form.assessment_content} onChange={(e) => update('assessment_content', e.target.value)} placeholder="写清楚发生时间、地点、问题、数量和考核依据，最多600字。" /><small>{form.assessment_content.length}/600</small></label>
      <div className="fields"><label>数量<input inputMode="numeric" required type="number" min="1" max="100000" step="1" value={form.quantity} onChange={(e) => update('quantity', e.target.value)} /></label><label>{employee ? '建议考核金额（元，主管复核）' : '处罚金额（元）'}<input inputMode="numeric" required type="number" min="1" max="100000000" step="1" value={form.penalty_amount} onChange={(e) => update('penalty_amount', e.target.value)} /></label></div>
      <div className="money"><div><span>金额大写</span><strong>{moneyCn}</strong><small>数量、金额必须是正整数，正式生成前由主管核实。</small></div></div>
      {employee ? <details className="optional-fields"><summary>分类与备注（可选）</summary>{classification}<label>备注<textarea value={form.remark} onChange={(e) => update('remark', e.target.value)} /></label></details> : <>{classification}<label>备注<textarea value={form.remark} onChange={(e) => update('remark', e.target.value)} /></label></>}
      <p className="helper-message">考核办法版本：{form.regulation_version || '20260819'}。{employee ? '当前为草稿，不产生正式考核编号。' : '文书归档成功才正式生效。'}</p>
      <div className="actions form-actions">{employee ? <button className="primary" disabled={busy || aiBusy}>{busy ? '正在保存…' : draft ? '更新填报草稿' : '保存填报草稿'}</button> : <><button type="button" disabled={busy || aiBusy} onClick={() => void save()}>{draft ? '更新草稿' : '保存草稿'}</button><button className="primary" disabled={busy || aiBusy}>{busy ? '正在处理…' : '复核并正式生成'}</button></>}</div>
    </fieldset></form>{!employee && <aside className="summary"><span>正式文书摘要</span><h2>{draft?.assessment_no || '待正式编号'}</h2><dl><div><dt>被考核单位</dt><dd>{form.assessment_unit_name || '未填写'}</dd></div><div><dt>班次 / 检查人</dt><dd>{form.shift} · {form.team}{form.inspector_name || '未选择'}</dd></div><div><dt>数量 / 金额</dt><dd>{form.quantity || '—'} · ¥ {formatMoney(form.penalty_amount)}</dd></div><div><dt>金额大写</dt><dd>{moneyCn}</dd></div><div><dt>考核事项</dt><dd>{form.assessment_content || '未填写'}</dd></div></dl></aside>}</div>
  </section>;
}

function PolicyAssistant({ aiEnabled }: { aiEnabled: boolean }) {
  const [question, setQuestion] = useState(''); const [answer, setAnswer] = useState<AiPolicyResult | null>(null); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false);
  const [rules, setRules] = useState<AssessmentRule[]>([]); const [keyword, setKeyword] = useState(''); const [ruleError, setRuleError] = useState('');
  useEffect(() => { let cancelled = false; let revision = 0;
    const refresh = () => { const current = ++revision; void loadRules().then((value) => { if (!cancelled && current === revision) { setRules(value); setRuleError(''); } }).catch((error: Error) => { if (!cancelled && current === revision) setRuleError(error.message); }); };
    refresh(); window.addEventListener('assessment-policy-changed', refresh); window.addEventListener('focus', refresh);
    return () => { cancelled = true; window.removeEventListener('assessment-policy-changed', refresh); window.removeEventListener('focus', refresh); };
  }, []);
  const matches = searchRules(rules, keyword);
  const submit = async (event: FormEvent) => { event.preventDefault(); if (!aiEnabled) return; setBusy(true); setMessage(''); setAnswer(null); try { setAnswer(await api<AiPolicyResult>('/ai/policy', { method: 'POST', body: JSON.stringify({ question }) })); } catch (error) { setMessage(error instanceof Error ? error.message : '制度问答失败。'); } finally { setBusy(false); } };
  return <section><Intro kicker="制度辅助" title="制度查询" text="先查看原始条款；考核依据和金额仍需人工核实。关键词查询不需要AI密钥。" />
    <section className="panel rule-search"><label>查询正式制度<input type="search" value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="输入环节、条款、问题关键词，例如：破损" /></label>
      {ruleError && <p className="error" role="alert">{ruleError}</p>}<p className="helper-message">{rules.length ? `共匹配 ${matches.length} 条，显示前30条；可继续输入关键词缩小范围。` : ruleError ? '制度文件未加载。' : '正在加载制度目录…'}</p>
      {matches.slice(0, 30).map((rule) => <details className="rule-item" key={rule.id}><summary>{rule.stage} · {rule.clause} · {rule.name}</summary><p className="pre">{rule.original}</p><small>制度版本：{rule.version}；{rule.needsSupervisorReview ? '需主管认定' : '适用条件与金额请以原文为准'}。</small></details>)}
    </section>
    <details className="panel policy-ai"><summary>AI制度问答（可选）{!aiEnabled && ' · 暂未启用'}</summary>{aiEnabled ? <form className="compact-form" onSubmit={submit}><label>问题<textarea required minLength={2} maxLength={1000} value={question} onChange={(e) => setQuestion(e.target.value)} /></label><button className="primary" disabled={busy}>{busy ? '正在查询…' : 'AI查询制度'}</button>{message && <p className="helper-message" role="alert">{message}</p>}{answer && <dl><div><dt>结论</dt><dd>{answer.conclusion}</dd></div><div><dt>建议</dt><dd>{answer.recommended_action}</dd></div><div><dt>后果/标准</dt><dd>{answer.consequence}</dd></div><div><dt>依据条款</dt><dd>{answer.rule_ids.length ? answer.rule_ids.join('、') : '未匹配到明确条款'}</dd></div><div><dt>主管复核</dt><dd>{answer.needs_supervisor_review ? '需要' : '不需要'}</dd></div></dl>}</form> : <p className="helper-message">服务端未配置DeepSeek密钥，请使用上方条款查询。</p>}</details>
  </section>;
}

function Ledger({ employee, canCreate, canExport, edit, data, search, setSearch, status, setStatus, load, selected, setSelected, copy, voidItem, canVoid, busy, say }: { employee: boolean; canCreate: boolean; canExport: boolean; edit: (item: Assessment) => Promise<void>; data: AssessmentPage; search: string; setSearch: (v: string) => void; status: string; setStatus: (v: string) => void; load: (page?: number) => Promise<void>; selected: Assessment | null; setSelected: (item: Assessment | null) => void; copy: (item: Assessment) => Promise<void>; voidItem: (item: Assessment) => Promise<void>; canVoid: boolean; busy: boolean; say: (type: 'success' | 'error', text: string) => void }) {
  const [loading, setLoading] = useState(false);
  const run = async (operation: () => Promise<void>) => { setLoading(true); try { await operation(); } catch (error) { say('error', error instanceof Error ? error.message : '操作失败。'); } finally { setLoading(false); } };
  const exportCurrent = () => { const q = new URLSearchParams(); if (search.trim()) q.set('keyword', search.trim()); if (status) q.set('status', status); return download(`/exports/assessment-ledger.xlsx?${q}`, '考核台账.xlsx'); };
  return <section><Intro kicker={employee ? '本人填报' : '统一台账'} title={employee ? '我的记录' : '考核台账'} text={employee ? '只显示你创建的记录；草稿可继续填写，正式记录不可修改。' : '主管可直接打开本部门草稿复核；正式生成后只允许作废，不允许改写。'} />
    <section className="panel"><form className="tools" onSubmit={(e) => { e.preventDefault(); void run(() => load(1)); }}><label><MagnifyingGlassIcon aria-hidden="true" /><input aria-label="查询记录关键词" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="编号、单位、检查人或事项" /></label><select aria-label="记录状态" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">全部状态</option><option value="draft">草稿</option><option value="effective">正式</option><option value="voided">已作废</option></select><button disabled={busy || loading}>查询</button>{canExport && <button type="button" disabled={busy || loading} onClick={() => void run(exportCurrent)}>导出 Excel</button>}</form>
      <RecordTable rows={data.items} actions={(item) => <><button onClick={() => setSelected(item)}>查看</button>{canCreate && item.status === 'draft' && <button disabled={busy || loading} onClick={() => void edit(item)}>{employee ? '继续填写' : '复核草稿'}</button>}{canCreate && <button disabled={busy || loading} onClick={() => void copy(item)}>复制</button>}{canVoid && item.status === 'effective' && <button className="danger" disabled={busy || loading} onClick={() => void voidItem(item)}>作废</button>}</>} />
      <div className="pagination"><span>共 {data.total} 条</span><div><button disabled={loading || data.page <= 1} onClick={() => void run(() => load(data.page - 1))}>上一页</button><span>第 {data.page} 页</span><button disabled={loading || data.page * data.page_size >= data.total} onClick={() => void run(() => load(data.page + 1))}>下一页</button></div></div>
    </section>{selected && <Detail key={selected.id} item={selected} close={() => setSelected(null)} />}
  </section>;
}
function Statistics({ overview, stats }: { overview: Overview | null; stats: { units: GroupStatistic[]; departments: GroupStatistic[]; categories: GroupStatistic[] } }) { return <section><Intro kicker="真实聚合" title="统计分析" text="仅统计正式考核单，每项数据均可回查考核台账。" /><div className="metrics compact"><article><span>本月考核次数</span><strong>{overview?.month_count || 0}<small>次</small></strong></article><article><span>本月处罚金额</span><strong>{formatMoney(overview?.month_amount || 0)}<small>元</small></strong></article></div><div className="stats"><Group title="按被考核单位" rows={stats.units} /><Group title="按部门" rows={stats.departments} /><Group title="按问题类型" rows={stats.categories} /></div><PeopleStatistics /></section>; }
function PeopleStatistics() {
  const [groups, setGroups] = useState<{ teams: GroupStatistic[]; people: GroupStatistic[] }>({ teams: [], people: [] });
  const [error, setError] = useState('');
  useEffect(() => { let active = true; void Promise.all([api<GroupStatistic[]>('/statistics/teams'), api<GroupStatistic[]>('/statistics/inspectors')]).then(([teams, people]) => { if (active) setGroups({ teams, people }); }).catch((cause: Error) => { if (active) setError(cause.message); }); return () => { active = false; }; }, []);
  return <><p className="helper-message">班组和姓名由填报内容自动归类，无需维护人员名单。</p>{error && <p className="error" role="alert">{error}</p>}<div className="stats"><Group title="按班组" rows={groups.teams} /><Group title="按姓名" rows={groups.people} /></div></>;
}

function Management({ refData, refreshReference, say }: { refData: ReferenceData; refreshReference: () => Promise<void>; say: (type: 'success' | 'error', text: string) => void }) {
  const [users, setUsers] = useState<ManagedUser[]>([]); const [catalog, setCatalog] = useState<ManagementCatalog | null>(null);
  const [account, setAccount] = useState({ username: '', display_name: '', password: '', role: 'employee', department_id: '' });
  const [item, setItem] = useState({ kind: 'departments', name: '', department_id: '', parent_name: '' });
  const lifetime = useRef(createRequestGate()).current;
  const load = async () => { const request = lifetime.capture(); const [nextUsers, nextCatalog] = await Promise.all([api<ManagedUser[]>('/management/users'), api<ManagementCatalog>('/management/catalog')]); if (lifetime.isCurrent(request)) { setUsers(nextUsers); setCatalog(nextCatalog); } };
  useEffect(() => { const request = lifetime.capture(); void load().catch((error: Error) => { if (lifetime.isCurrent(request)) say('error', error.message); }); return () => { lifetime.invalidate(); }; }, []);
  const createAccount = async (event: FormEvent) => { event.preventDefault(); const request = lifetime.capture(); try { await api('/management/users', { method: 'POST', body: JSON.stringify({ ...account, department_id: account.department_id ? Number(account.department_id) : null }) }); if (!lifetime.isCurrent(request)) return; setAccount({ username: '', display_name: '', password: '', role: 'employee', department_id: '' }); await load(); if (lifetime.isCurrent(request)) say('success', '账号已创建。'); } catch (error) { if (lifetime.isCurrent(request)) say('error', error instanceof Error ? error.message : '创建失败。'); } };
  const toggleUser = async (value: ManagedUser) => { const request = lifetime.capture(); try { await api(`/management/users/${value.id}`, { method: 'PUT', body: JSON.stringify({ display_name: value.display_name, role: value.role, department_id: value.department_id, active: !value.active, password: null }) }); if (!lifetime.isCurrent(request)) return; await load(); if (lifetime.isCurrent(request)) say('success', `账号已${value.active ? '停用' : '启用'}。`); } catch (error) { if (lifetime.isCurrent(request)) say('error', error instanceof Error ? error.message : '更新失败。'); } };
  const createItem = async (event: FormEvent) => { event.preventDefault(); const request = lifetime.capture(); try { await api(`/management/${item.kind}`, { method: 'POST', body: JSON.stringify({ name: item.name, department_id: item.department_id ? Number(item.department_id) : null, parent_name: item.parent_name || null }) }); if (!lifetime.isCurrent(request)) return; setItem((old) => ({ ...old, name: '', parent_name: '' })); await Promise.all([load(), refreshReference()]); if (lifetime.isCurrent(request)) say('success', '基础数据已新增。'); } catch (error) { if (lifetime.isCurrent(request)) say('error', error instanceof Error ? error.message : '新增失败。'); } };
  const rows = catalog ? [...catalog.departments.map((v) => ({ ...v, kind: 'departments', group: '部门' })), ...catalog.units.map((v) => ({ ...v, kind: 'units', group: '被考核单位' })), ...catalog.categories.map((v) => ({ ...v, kind: 'categories', group: '问题分类' })), ...catalog.master_items.map((v) => ({ ...v, kind: ({ shift: 'shifts', team: 'teams', inspector: 'inspectors', operation_stage: 'operation-stages' } as Record<string, string>)[v.kind || ''] || 'operation-stages', group: ({ shift: '班次', team: '班组', inspector: '检查人', operation_stage: '作业环节' } as Record<string, string>)[v.kind || ''] || '作业环节' }))] : [];
  const toggleItem = async (value: typeof rows[number]) => { const request = lifetime.capture(); try { await api(`/management/${value.kind}/${value.id}/active`, { method: 'PUT', body: JSON.stringify({ active: !value.active }) }); if (!lifetime.isCurrent(request)) return; await Promise.all([load(), refreshReference()]); if (lifetime.isCurrent(request)) say('success', '基础数据状态已更新。'); } catch (error) { if (lifetime.isCurrent(request)) say('error', error instanceof Error ? error.message : '更新失败。'); } };
  return <section><Intro kicker="权限与基础数据" title="系统管理" text="新增、启停与密码初始化均由管理员执行并写入审计日志；历史考核单保留名称快照。" /><div className="management-grid"><form className="panel compact-form" onSubmit={createAccount}><h2>新增账号</h2><label>用户名<input required minLength={3} value={account.username} onChange={(e) => setAccount({ ...account, username: e.target.value })} /></label><label>显示姓名<input required value={account.display_name} onChange={(e) => setAccount({ ...account, display_name: e.target.value })} /></label><label>初始密码<input required minLength={10} type="password" autoComplete="new-password" value={account.password} onChange={(e) => setAccount({ ...account, password: e.target.value })} /></label><label>角色<select value={account.role} onChange={(e) => setAccount({ ...account, role: e.target.value })}><option value="employee">职工</option><option value="department_manager">主管</option><option value="leader">领导（只读，兼容旧账号）</option><option value="admin">系统管理员</option></select></label><label>所属部门<select required={account.role === 'employee' || account.role === 'department_manager'} value={account.department_id} onChange={(e) => setAccount({ ...account, department_id: e.target.value })}><option value="">不绑定部门</option>{refData.departments.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label><button className="primary">创建账号</button></form><form className="panel compact-form" onSubmit={createItem}><h2>新增基础数据</h2><label>类型<select value={item.kind} onChange={(e) => setItem({ ...item, kind: e.target.value, parent_name: '' })}><option value="departments">部门</option><option value="units">被考核单位</option><option value="categories">问题分类</option><option value="shifts">班次</option><option value="teams">班组</option><option value="inspectors">检查人</option><option value="operation-stages">作业环节</option></select></label><label>名称<input required value={item.name} onChange={(e) => setItem({ ...item, name: e.target.value })} /></label>{item.kind === 'units' && <label>所属部门<select required value={item.department_id} onChange={(e) => setItem({ ...item, department_id: e.target.value })}><option value="">请选择</option>{refData.departments.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>}{item.kind === 'inspectors' && <label>所属班组<select required value={item.parent_name} onChange={(e) => setItem({ ...item, parent_name: e.target.value })}><option value="">请选择</option>{refData.teams.map((v) => <option key={v}>{v}</option>)}</select></label>}<button className="primary">新增数据</button></form></div><section className="panel"><h2>账号列表</h2><div className="table-wrap"><table><thead><tr><th>用户名</th><th>姓名</th><th>角色</th><th>部门</th><th>状态</th><th>操作</th></tr></thead><tbody>{users.map((v) => <tr key={v.id}><td>{v.username}</td><td>{v.display_name}</td><td>{roleName(v.role)}</td><td>{refData.departments.find((d) => d.id === v.department_id)?.name || '—'}</td><td>{v.active ? '启用' : '停用'}</td><td><button onClick={() => void toggleUser(v)}>{v.active ? '停用' : '启用'}</button></td></tr>)}</tbody></table></div></section><section className="panel"><h2>基础数据状态</h2><div className="table-wrap"><table><thead><tr><th>类型</th><th>名称</th><th>归属</th><th>状态</th><th>操作</th></tr></thead><tbody>{rows.map((v) => <tr key={`${v.kind}-${v.id}`}><td>{v.group}</td><td>{v.name}</td><td>{v.parent_name || '—'}</td><td>{v.active ? '启用' : '停用'}</td><td><button onClick={() => void toggleItem(v)}>{v.active ? '停用' : '启用'}</button></td></tr>)}</tbody></table></div></section></section>;
}
function Intro({ kicker, title, text }: { kicker: string; title: string; text: string }) { return <div className="intro"><p>{kicker}</p><h1>{title}</h1><span>{text}</span></div>; }
function Detail({ item, close }: { item: Assessment; close: () => void }) {
  const [pdfUrl, setPdfUrl] = useState(''); const [fileError, setFileError] = useState(''); const [fileBusy, setFileBusy] = useState(false);
  const gate = useRef(createRequestGate()).current; const currentUrl = useRef('');
  useEffect(() => () => { gate.invalidate(); if (currentUrl.current) URL.revokeObjectURL(currentUrl.current); }, [gate]);
  const fetchFile = async (kind: 'word' | 'pdf' | 'preview') => {
    if (fileBusy) return;
    const request = gate.invalidate(); setFileError(''); setFileBusy(true);
    try {
      if (kind === 'preview') {
        const next = await loadBlobUrl(`/assessments/${item.id}/documents/pdf`);
        if (!gate.isCurrent(request)) { URL.revokeObjectURL(next); return; }
        if (currentUrl.current) URL.revokeObjectURL(currentUrl.current);
        currentUrl.current = next; setPdfUrl(next);
      } else await download(`/assessments/${item.id}/documents/${kind}`, `${item.assessment_no}.${kind === 'word' ? 'docx' : 'pdf'}`);
    } catch (error) { if (gate.isCurrent(request)) setFileError(error instanceof Error ? error.message : '文件读取失败。'); }
    finally { if (gate.isCurrent(request)) setFileBusy(false); }
  };
  return <section className="panel detail"><div className="panel-head"><div><h2>{item.assessment_no || `草稿 #${item.id}`}</h2><p><b className={`status ${item.status}`}>{statusName(item.status)}</b></p></div><button onClick={close}>关闭</button></div>
    <dl><div><dt>发生日期</dt><dd>{item.incident_date} · {item.shift}</dd></div><div><dt>班组 / 检查人</dt><dd>{item.team} · {item.inspector_name}</dd></div><div><dt>被考核单位</dt><dd>{item.assessment_unit_name_snapshot}</dd></div><div><dt>数量</dt><dd>{item.quantity}</dd></div><div><dt>处罚金额</dt><dd>¥ {formatMoney(item.penalty_amount)}（{item.penalty_amount_cn}）</dd></div><div><dt>考核事项</dt><dd className="pre">{item.assessment_content}</dd></div><div><dt>备注</dt><dd className="pre">{item.remark || '—'}</dd></div>{item.void_reason && <div><dt>作废原因</dt><dd>{item.void_reason}</dd></div>}</dl>
    {item.status !== 'draft' && <div className="actions"><button disabled={fileBusy} onClick={() => void fetchFile('word')}>下载Word</button><button className="primary" disabled={fileBusy} onClick={() => void fetchFile('preview')}>{fileBusy ? '正在读取…' : '预览PDF'}</button><button disabled={fileBusy} onClick={() => void fetchFile('pdf')}>下载PDF</button></div>}
    {fileError && <p className="helper-message error" role="alert">{fileError}</p>}{pdfUrl && <iframe className="pdf-preview" title={`${item.assessment_no} PDF预览`} src={pdfUrl} />}
  </section>;
}
function Group({ title, rows }: { title: string; rows: GroupStatistic[] }) { return <section className="panel"><h2>{title}</h2>{rows.length ? <table><thead><tr><th>名称</th><th>次数</th><th>金额</th></tr></thead><tbody>{rows.map((v) => <tr key={v.name}><td>{v.name}</td><td>{v.count}</td><td>¥ {formatMoney(v.amount)}</td></tr>)}</tbody></table> : <p className="empty">暂无正式考核数据。</p>}</section>; }
export default App;
