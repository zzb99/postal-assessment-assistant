import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { Assessment, AssessmentPage } from '../api';
import { amountToChinese, formatMoney } from '../utils/money';
import { clearRequest, readIdentity, rememberIdentity, requestIdFor } from './identity';
import { quickApi, quickFile } from './api';
import { imageFromPdf, saveFile, sharePreparedFile } from './share';
import { mergeRecent } from './history';
import { AiComposer } from './AiComposer';
import { readDraft, saveDraft, clearDraft, readSessionProposal, saveSessionProposal, clearSessionProposal } from './draft';
import '../app.css';
import './quick.css';

type Config = { units: Array<{ id: number; name: string }>; shifts: string[]; ai_enabled: boolean; regulation_version: string };
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date());
const initial = (restore = true) => {
  const data = { incident_date: today(), shift: '白班', unit: '', facts: '', quantity: '', penalty_amount: '', assessment_content: '', ...(restore ? readDraft() : {}), team: readIdentity().team, inspector_name: readIdentity().name, ai_proposal: '' };
  const saved = restore ? readSessionProposal(data) : null;
  return { ...data, ai_proposal: saved?.token || '' };
};

export default function QuickPage() {
  const [config, setConfig] = useState<Config | null>(null);
  const [form, setForm] = useState(() => initial());
  const [item, setItem] = useState<Assessment | null>(null);
  const [records, setRecords] = useState<Assessment[]>([]);
  const [busy, setBusy] = useState(false); const [preparing, setPreparing] = useState(false);
  const [aiBusy, setAiBusy] = useState(false); const [manual, setManual] = useState(false);
  const [signedContent, setSignedContent] = useState(() => readSessionProposal(initial())?.signedContent || ''); const [editConfirmed, setEditConfirmed] = useState(false);
  const [draftSaved, setDraftSaved] = useState(true);
  const [error, setError] = useState(''); const [hint, setHint] = useState(''); const [storageWarning, setStorageWarning] = useState(false);
  const [pdf, setPdf] = useState<File | null>(null); const [image, setImage] = useState<File | null>(null); const [imageUrl, setImageUrl] = useState('');
  const [wordBusy, setWordBusy] = useState(false); const wordController = useRef<AbortController | null>(null);
  const alive = useRef(true); const operation = useRef(false); const fileRequest = useRef(0); const fileController = useRef<AbortController | null>(null);
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    void quickApi<Config>('/config', { signal: controller.signal }).then((value) => { if (alive.current) setConfig(value); }).catch((cause: Error) => { if (alive.current) setError(`无法连接填报服务：${cause.message}`); });
    void quickApi<AssessmentPage>('/assessments', { signal: controller.signal }).then((value) => { if (alive.current) setRecords((old) => mergeRecent(old, value.items)); }).catch((cause: Error) => { if (alive.current) setHint(`本机记录暂未加载：${cause.message}`); });
    return () => { alive.current = false; controller.abort(); fileController.current?.abort(); wordController.current?.abort(); fileRequest.current++; };
  }, []);
  useEffect(() => { setStorageWarning(!rememberIdentity({ team: form.team, name: form.inspector_name })); }, [form.team, form.inspector_name]);
  useEffect(() => { if (!item) { setDraftSaved(saveDraft(form)); saveSessionProposal(form, signedContent); } }, [form, item, signedContent]);
  useEffect(() => () => { if (imageUrl) URL.revokeObjectURL(imageUrl); }, [imageUrl]);
  const update = (key: keyof typeof form, value: string) => setForm((old) => ({ ...old, [key]: value }));
  const invalidateAi = () => { clearSessionProposal(); setEditConfirmed(false); setForm((old) => old.ai_proposal ? { ...old, ai_proposal: '' } : old); };
  const canGenerate = Boolean(form.team.trim() && form.inspector_name.trim() && form.unit && form.incident_date && (manual ? editConfirmed : form.ai_proposal) && form.assessment_content.trim() && Number(form.quantity) > 0 && Number(form.penalty_amount) > 0);

  const prepare = async (value: Assessment) => {
    wordController.current?.abort(); setWordBusy(false);
    fileController.current?.abort(); const controller = new AbortController(); fileController.current = controller;
    const request = ++fileRequest.current; const valid = () => alive.current && request === fileRequest.current;
    setPreparing(true); setPdf(null); setImage(null); setImageUrl(''); setHint('正在准备可分享的文件…');
    try {
      const file = await quickFile(value.id, 'pdf', `${value.assessment_no}.pdf`, controller.signal);
      if (!valid()) return; setPdf(file);
      try {
        const png = await imageFromPdf(file); if (!valid()) return;
        setImage(png); setImageUrl(URL.createObjectURL(png)); setHint('点击“分享到群”，在手机分享菜单中选择微信或其他应用。');
      } catch (cause) { if (valid()) setHint(`PDF已就绪，图片暂不可用：${cause instanceof Error ? cause.message : '请下载PDF发群。'}`); }
    } catch (cause) { if (valid()) setHint(`文书已保存，文件准备失败，可点击重新加载：${cause instanceof Error ? cause.message : '网络异常'}`); }
    finally { if (valid()) setPreparing(false); }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (operation.current || aiBusy || !config || !canGenerate || (!manual && !form.ai_proposal)) return;
    operation.current = true; setBusy(true); setError(''); setHint('');
    const unit = config.units.find((value) => String(value.id) === form.unit);
    const payload = { incident_date: form.incident_date, shift: form.shift, team: form.team.trim(), inspector_name: form.inspector_name.trim(), assessment_unit_id: unit?.id, assessment_unit_name: unit?.name || '', quantity: Number(form.quantity), penalty_amount: form.penalty_amount, assessment_content: form.assessment_content.trim(), ...(form.ai_proposal ? { ai_proposal: form.ai_proposal } : {}) };
    try {
      if (!manual && form.assessment_content !== signedContent) {
        if (!editConfirmed) throw new Error('请勾选核对修改后的事实，再生成。');
        const original = { ...payload, assessment_content: signedContent, request_id: crypto.randomUUID() };
        const confirmed = await quickApi<{ proposal_token: string }>('/ai/reconfirm', { method: 'POST', body: JSON.stringify({ original, edited_content: form.assessment_content, facts_confirmed: true }) });
        payload.ai_proposal = confirmed.proposal_token;
        setSignedContent(form.assessment_content); update('ai_proposal', confirmed.proposal_token);
      }
      const request_id = await requestIdFor(payload);
      if (!alive.current) return;
      const result = await quickApi<Assessment>('/assessments', { method: 'POST', body: JSON.stringify({ ...payload, request_id }) });
      if (!alive.current) return;
      setItem(result); setRecords((old) => [result, ...old.filter((value) => value.id !== result.id)].slice(0, 10));
      clearDraft(); clearSessionProposal();
      setForm((old) => ({ ...old, team: result.team, inspector_name: result.inspector_name }));
      window.scrollTo({ top: 0 });
      if (result.status === 'effective') await prepare(result); else setHint('这条记录已作废或未正式生成，请新建单据。');
    } catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : '生成失败，输入内容仍然保留，可重试。'); }
    finally { if (alive.current) { operation.current = false; setBusy(false); } }
  };

  const share = async () => {
    const file = image || pdf; if (!file) return;
    try {
      const state = await sharePreparedFile(file);
      if (!alive.current) return;
      if (state === 'unsupported') setHint('当前浏览器不支持直接分享文件。请保存图片，再到微信/QQ群发送；也可长按下方图片保存。');
      else if (state === 'shared') setHint('文件已交给系统分享菜单；是否发送到群以你在应用中的操作为准。');
      else setHint('已取消分享，文件仍在，可以重新分享。');
    } catch (cause) { if (alive.current) setHint(`无法直接分享：${cause instanceof Error ? cause.message : '请先保存图片，再发群。'}`); }
  };
  const word = async () => {
    if (!item || wordBusy) return;
    const request = fileRequest.current; const controller = new AbortController(); wordController.current = controller;
    const valid = () => alive.current && fileRequest.current === request;
    setWordBusy(true);
    try { const file = await quickFile(item.id, 'word', `${item.assessment_no}.docx`, controller.signal); if (valid()) saveFile(file); }
    catch (cause) { if (valid()) setHint(cause instanceof Error ? cause.message : 'Word下载失败'); }
    finally { if (valid()) setWordBusy(false); }
  };
  const newNotice = () => { fileRequest.current++; fileController.current?.abort(); wordController.current?.abort(); setWordBusy(false); clearRequest(); clearDraft(); clearSessionProposal(); setManual(false); setEditConfirmed(false); setItem(null); setPdf(null); setImage(null); setImageUrl(''); setPreparing(false); setError(''); setHint(''); setForm((old) => ({ ...initial(false), team: old.team, inspector_name: old.inspector_name, shift: old.shift, unit: old.unit })); };

  return <div className="quick-page"><header className="quick-header"><strong><span>邮</span>通信生产考核</strong><a href="#manage">后台管理</a></header><main className="quick-main">
    {error && <p className="error" role="alert">{error}</p>}
    {storageWarning && <p className="helper-message">浏览器未允许记住信息，关闭后可能需重新填写班组和姓名。</p>}
    {!item ? <><div className="quick-title"><h1>填写考核单</h1><p>描述现场问题，核对后生成，直接发群。</p></div>
      <form className="panel form quick-form" onSubmit={submit}><fieldset className="form-fields" disabled={busy || aiBusy || !config}>
        <div className="quick-step"><span>1</span><strong>填写信息</strong><small>班组、姓名自动记住</small></div>
        <div className="fields"><label>班组<input required maxLength={32} autoComplete="organization" value={form.team} onChange={(e) => update('team', e.target.value)} placeholder="自己填写，例如二班" /></label><label>姓名<input required maxLength={100} autoComplete="name" value={form.inspector_name} onChange={(e) => update('inspector_name', e.target.value)} placeholder="填写你的姓名" /></label>
          <label>检查日期<input required type="date" value={form.incident_date} onChange={(e) => update('incident_date', e.target.value)} /></label><label>班次<select required value={form.shift} onChange={(e) => update('shift', e.target.value)}>{(config?.shifts || ['白班', '夜班']).map((value) => <option key={value}>{value}</option>)}</select></label></div>
        <label>被考核公司<select required value={form.unit} onChange={(e) => update('unit', e.target.value)}><option value="">请选择公司</option>{config?.units.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</select></label>
        <AiComposer enabled={config?.ai_enabled || false} disabled={busy || !config} manual={manual} context={{ incident_date: form.incident_date, shift: form.shift, assessment_unit_id: Number(form.unit) }} facts={form.facts} onFacts={(facts) => update('facts', facts)} onDraft={(content) => setForm((old) => ({ ...old, assessment_content: content, quantity: '', penalty_amount: '' }))} onPending={setAiBusy} onInvalidate={invalidateAi} onPrepared={(value) => { setForm((old) => ({ ...old, ...value })); setSignedContent(value.assessment_content); setEditConfirmed(false); setError(''); }}>
        <div className="quick-review-heading"><div className="quick-step"><span>3</span><strong>核对考核单</strong></div><button type="button" className="quick-mode" disabled={busy || aiBusy} onClick={() => { setManual((old) => !old); invalidateAi(); }}>{manual ? '返回AI整理' : form.assessment_content ? '手动调整' : '手动填写'}</button></div>
        {(manual || form.assessment_content) ? <><label>{manual ? '考核正文 · 手动调整' : form.ai_proposal ? '考核正文 · 可核对修改' : '正文草稿 · 待核定金额'}<textarea readOnly={!manual && !form.ai_proposal} required maxLength={600} value={form.assessment_content} onChange={(e) => { update('assessment_content', e.target.value); setEditConfirmed(false); }} placeholder="填写现场事实、制度依据、考核金额及整改要求。" /><small>{form.assessment_content.length}/600</small></label>
        {!manual && form.ai_proposal && signedContent !== form.assessment_content && <label className="quick-confirm"><input type="checkbox" checked={editConfirmed} onChange={(e) => setEditConfirmed(e.target.checked)} />修改内容已核对，事实、条款和金额未改变。</label>}
        {(manual || form.ai_proposal) && <><div className="fields"><label>数量<input required readOnly={!manual} inputMode="numeric" type="number" min={1} max={100000} step={1} value={form.quantity} onChange={(e) => { update('quantity', e.target.value); setEditConfirmed(false); }} /></label><label>考核金额（元）<input required readOnly={!manual} inputMode="numeric" type="number" min={1} max={100000000} step={1} value={form.penalty_amount} onChange={(e) => { update('penalty_amount', e.target.value); setEditConfirmed(false); }} /></label></div>
        <p className="quick-money">大写：{form.penalty_amount ? amountToChinese(form.penalty_amount) : '待填写金额'}</p>
        {manual && <label className="quick-confirm"><input type="checkbox" checked={editConfirmed} onChange={(e) => setEditConfirmed(e.target.checked)} />正文、制度依据和金额已核对。</label>}</>}
        </> : <p className="quick-empty">整理完成后，正文和金额会显示在这里。</p>}
        </AiComposer>
        <p className="quick-draft-status" role="status">{draftSaved ? '草稿已自动保存；同一标签页短时间刷新可恢复AI确认，过期需重新核对。' : '本机无法保存草稿，请复制正文后再离开页面。'}</p>
        <div className="quick-submit"><button className="primary" disabled={busy || aiBusy || !config || !canGenerate || (!manual && signedContent !== form.assessment_content && !editConfirmed)}>{busy ? '正在排队生成Word与PDF，请勿重复点击…' : '生成考核单'}</button>
          {!canGenerate && <small>{!form.team.trim() || !form.inspector_name.trim() || !form.unit ? '请填写班组、姓名，并选择被考核公司。' : manual ? '请补全正文、数量和金额，并勾选核对。' : '整理并核对正文和金额后，即可生成。'}</small>}
        </div>
      </fieldset></form></> : <section className="quick-result"><div className="quick-title"><h1>{item.status === 'effective' ? '考核单已生成' : '考核单状态已变化'}</h1><p>{item.assessment_no || `草稿 #${item.id}`} · {item.team} · {item.inspector_name}</p></div>
      <div className="quick-share-actions"><button className="primary" disabled={!pdf || preparing || item.status !== 'effective'} onClick={() => void share()}>{preparing ? '正在准备分享文件…' : '分享到群'}</button><button disabled={!image || preparing} onClick={() => { if (image) saveFile(image); }}>保存图片</button></div>
      {hint && <p className="helper-message" role="status">{hint}</p>}
      {item.status === 'effective' && !preparing && !pdf && <button onClick={() => void prepare(item)}>重新加载文书</button>}
      {imageUrl && <img className="quick-document" src={imageUrl} alt={`${item.assessment_no}正式考核单，可长按保存发群`} />}
      <details className="quick-more"><summary>下载文件 / 复制文字</summary><div className="actions"><button disabled={!pdf} onClick={() => { if (pdf) saveFile(pdf); }}>下载PDF</button><button disabled={item.status !== 'effective' || wordBusy} onClick={() => void word()}>下载Word</button><button onClick={() => { const text = `${item.assessment_no}\n${item.team} ${item.inspector_name}\n${item.incident_date} ${item.shift}\n${item.assessment_unit_name_snapshot}\n${item.assessment_content}\n数量：${item.quantity}；考核金额：${formatMoney(item.penalty_amount)}元`; if (navigator.clipboard) void navigator.clipboard.writeText(text).then(() => { if (alive.current) setHint('文字已复制，可粘贴到群里。'); }).catch(() => { if (alive.current) setHint('复制失败，请下载文件或保存图片。'); }); else setHint('当前浏览器不支持复制，请下载文件或保存图片。'); }}>复制文字</button></div></details>
      <button className="quick-next" disabled={busy} onClick={newNotice}>再填一张</button>
    </section>}
    {!item && hint && <p className="helper-message" role="status">{hint}</p>}
    {!item && records.length > 0 && <details className="quick-history"><summary>本机最近单据</summary>{records.map((value) => <button disabled={busy} key={value.id} onClick={() => { setItem(value); setError(''); window.scrollTo({ top: 0 }); if (value.status === 'effective') void prepare(value); else setHint('此记录未正式生成或已作废，请新建。'); }}><span>{value.assessment_no || '未生成'} · {value.assessment_unit_name_snapshot}</span><small>{value.incident_date} · {value.team} · {value.inspector_name} · ¥{formatMoney(value.penalty_amount)}</small></button>)}</details>}
  </main></div>;
}
