import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BookOpenIcon, ChevronLeftIcon, ChevronRightIcon, DocumentArrowDownIcon, DocumentTextIcon, ExclamationTriangleIcon, InformationCircleIcon, MagnifyingGlassIcon, PrinterIcon, SparklesIcon } from '@heroicons/react/24/outline';
import type { AssessmentForm, AssessmentRule, ExportState, FieldErrors, PricingOption } from './types';
import { loadRules } from './data/rules';
import { buildDocumentData } from './services/documentData';
import { hasErrors, MAX_FACT_LENGTH, validateForm } from './utils/validation';
import { clearDraft, loadDraft, saveDraft } from './utils/storage';
import { NoticePreview } from './components/NoticePreview';
import { PreviewPane } from './components/PreviewPane';
import { analyseWithDeepSeek, askPolicyWithDeepSeek, type AiPolicyAnswer } from './services/deepseekService';
import { DEEPSEEK_API_KEY } from './config/deepseek';
import './styles.css';
import './template.css';

const today = new Date().toISOString().slice(0, 10);
const initialForm: AssessmentForm = { noticeNo: `KH${today.replaceAll('-', '')}`, date: today, shift: '白班', company: '', inspector: '', stage: '', ruleId: '', pricingId: '', quantity: '1', fact: '' };
const companies = ['华洋公司', '联智公司', '君喜公司'];
const inspectors = ['一班吴正一', '二班黄旭东', '三班魏振'];

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="work-field"><span>{label}</span><div>{children}{error && <small className="field-error">{error}</small>}</div></label>;
}

function App() {
  const [tab, setTab] = useState<'create' | 'ask'>('create');
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(() => loadDraft(initialForm));
  const [rules, setRules] = useState<AssessmentRule[]>([]);
  const [ruleError, setRuleError] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [question, setQuestion] = useState('');
  const [policyAnswer, setPolicyAnswer] = useState<AiPolicyAnswer | null>(null);
  const [policyState, setPolicyState] = useState<ExportState>('idle');
  const [policyMessage, setPolicyMessage] = useState('');
  const [exportState, setExportState] = useState<ExportState>('idle');
  const [exportMessage, setExportMessage] = useState('');
  const [aiState, setAiState] = useState<ExportState>('idle');
  const [aiMessage, setAiMessage] = useState('');
  const [previewZoom, setPreviewZoom] = useState(100);
  const previewRef = useRef<HTMLElement | null>(null);

  useEffect(() => { loadRules().then(setRules).catch((error: Error) => setRuleError(error.message)); }, []);
  useEffect(() => { const id = setTimeout(() => saveDraft(form), 800); return () => clearTimeout(id); }, [form]);

  const selectedRule = rules.find((item) => item.id === form.ruleId);
  const selectedPricing = selectedRule?.pricingOptions.find((item) => item.id === form.pricingId);
  const documentData = selectedRule && selectedPricing && selectedPricing.unitPrice !== null ? buildDocumentData(form, selectedRule, selectedPricing) : undefined;
  const stages = useMemo(() => [...new Set(rules.map((item) => item.stage))], [rules]);
  const stageRules = rules.filter((item) => item.stage === form.stage);
  const matched = useMemo(() => policyAnswer ? rules.filter((rule) => policyAnswer.ruleIds.includes(rule.id)) : [], [policyAnswer, rules]);

  const update = (key: keyof AssessmentForm, value: string) => {
    setForm((old) => ({ ...old, [key]: value, ...(key === 'stage' ? { ruleId: '', pricingId: '' } : {}), ...(key === 'ruleId' ? { pricingId: '' } : {}) }));
    setErrors((old) => ({ ...old, [key]: undefined }));
  };
  const validateBasics = () => {
    const next = validateForm(form, undefined, undefined, ['company', 'inspector']);
    setErrors({ company: next.company, inspector: next.inspector });
    return !next.company && !next.inspector;
  };
  const verify = () => { const next = validateForm(form, selectedRule, selectedPricing); setErrors(next); return !hasErrors(next); };
  const next = () => { if (step === 1 && !validateBasics()) return; if (step === 2 && !verify()) return; setStep((value) => Math.min(3, value + 1)); };

  const runAiAssessment = async () => {
    if (!form.fact.trim()) { setErrors((old) => ({ ...old, fact: '请先填写事实经过，AI 才能识别考核情形。' })); return; }
    setAiState('loading'); setAiMessage('DeepSeek 正在依据正式制度识别考核情形…');
    try {
      const result = await analyseWithDeepSeek(DEEPSEEK_API_KEY, form.fact, rules);
      const rule = rules.find((item) => item.id === result.ruleId);
      const pricing = rule?.pricingOptions.find((item) => item.id === result.pricingId);
      if (!rule || !pricing) throw new Error('AI 未匹配到可用制度条款，请补充事实或改为主管认定。');
      setForm((old) => ({ ...old, stage: rule.stage, ruleId: rule.id, pricingId: pricing.id, quantity: result.quantity }));
      setAiState('success');
      setAiMessage(`${result.confidence === 'high' ? '已匹配' : '建议匹配'}：${rule.clause} · ${rule.name}。${result.reason}${result.needsSupervisorReview ? ' 该结果须主管最终认定。' : ''}`);
    } catch (error) { setAiState('error'); setAiMessage(error instanceof Error ? error.message : 'AI 识别失败，请重试。'); }
  };
  const runPolicyQuery = async () => {
    if (!question.trim()) { setPolicyState('error'); setPolicyMessage('请先输入想问的事情。'); return; }
    setPolicyState('loading'); setPolicyMessage('DeepSeek 正在阅读制度并整理回答…'); setPolicyAnswer(null);
    try {
      const answer = await askPolicyWithDeepSeek(DEEPSEEK_API_KEY, question.trim(), rules);
      setPolicyAnswer(answer); setPolicyState('success'); setPolicyMessage('已依据正式制度完成查询。');
    } catch (error) { setPolicyState('error'); setPolicyMessage(error instanceof Error ? error.message : '制度问答失败，请重试。'); }
  };
  const exportFile = async (kind: 'word' | 'pdf') => {
    if (!verify() || !documentData) { setStep(2); return; }
    setExportState('loading'); setExportMessage(`正在生成 ${kind === 'word' ? 'Word' : 'PDF'}…`);
    try {
      const { exportPdf, exportWord } = await import('./services/exportService');
      if (kind === 'word') await exportWord(documentData);
      else await exportPdf(documentData);
      setExportState('success'); setExportMessage(`${kind === 'word' ? 'Word' : 'PDF'} 已生成并开始下载。`);
    } catch (error) { setExportState('error'); setExportMessage(error instanceof Error ? error.message : '导出失败，请重试。'); }
  };

  const basics = <div className="basic-grid">
    <Field label="考核日期"><input type="date" value={form.date} onChange={(e) => update('date', e.target.value)} /></Field>
    <Field label="班次"><select value={form.shift} onChange={(e) => update('shift', e.target.value)}><option>白班</option><option>夜班</option></select></Field>
    <Field label="被考核工段/单位" error={errors.company}><select value={form.company} onChange={(e) => update('company', e.target.value)}><option value="">请选择</option>{companies.map((item) => <option key={item}>{item}</option>)}</select></Field>
    <Field label="考核人员" error={errors.inspector}><select value={form.inspector} onChange={(e) => update('inspector', e.target.value)}><option value="">请选择</option>{inspectors.map((item) => <option key={item}>{item}</option>)}</select></Field>
  </div>;
  const assessment = <>
    <label className="fact-field"><span>事实经过 <b>*</b></span><textarea maxLength={MAX_FACT_LENGTH} value={form.fact} onChange={(e) => update('fact', e.target.value)} placeholder="请写明作业地点/环节、邮件或事件信息和现场情况；日期、班次、被考核单位会自动写入考核事项。" />{errors.fact && <small className="field-error">{errors.fact}</small>}<small className="counter">{form.fact.length}/{MAX_FACT_LENGTH}</small></label>
    <div className="selection-sources">
      <section className={`ai-source ${aiState === 'error' ? 'warning' : ''}`}><div className="source-heading"><div><SparklesIcon /><strong>AI 智能识别</strong></div><span>自动匹配制度</span></div><p>根据事实经过推荐条款、计费单位与数量，结果请与手动调整对照核验。</p><button className="ai-button" onClick={runAiAssessment} disabled={aiState === 'loading'}><SparklesIcon />{aiState === 'loading' ? 'AI 正在分析…' : 'AI 分析考核依据'}</button>{aiMessage && <p className="ai-message">{aiMessage}</p>}</section>
      <section className="manual-panel"><div className="source-heading"><div><DocumentTextIcon /><strong>手动调整</strong></div><span>可随时修改</span></div><p>也可以直接选择作业环节、违规类型和计费标准。</p><div className="manual-grid">
        <Field label="作业环节" error={errors.stage}><select value={form.stage} onChange={(e) => update('stage', e.target.value)}><option value="">请选择</option>{stages.map((item) => <option key={item}>{item}</option>)}</select></Field>
        <Field label="违规类型" error={errors.ruleId}><select value={form.ruleId} disabled={!form.stage} onChange={(e) => update('ruleId', e.target.value)}><option value="">请选择</option>{stageRules.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
        <Field label="计费单位与单价" error={errors.pricingId}><select value={form.pricingId} disabled={!selectedRule} onChange={(e) => update('pricingId', e.target.value)}><option value="">请选择</option>{selectedRule?.pricingOptions.map((item) => <option value={item.id} key={item.id}>{item.unitPrice === null ? '主管最终认定' : `${item.unit} · ${item.unitPrice}元/${item.unit}`}（{item.condition}）</option>)}</select></Field>
      </div></section>
    </div>
    {selectedRule && <section className="analysis-card">
      <div className="analysis-title"><strong>最终考核依据</strong>{aiState === 'success' && <em>AI 已提供建议</em>}</div>
      {selectedRule && selectedPricing && <div className="analysis-table">
        <span>作业环节</span><b>{selectedRule.stage}</b><span>违规类型</span><b>{selectedRule.name}</b>
        <span>制度依据</span><b>{selectedRule.clause} · {selectedRule.original}</b><span>计费单位</span><b>{selectedPricing.unit}</b>
        <span>数量</span><b><input aria-label="数量" inputMode="numeric" value={form.quantity} onChange={(e) => update('quantity', e.target.value)} />{errors.quantity && <small className="field-error">{errors.quantity}</small>}</b><span>单价</span><b>{selectedPricing.unitPrice}元/{selectedPricing.unit}</b>
      </div>}
      {documentData && <div className="amount-total"><span>考核金额</span><strong>{documentData.amount}<small>元</small></strong></div>}
      {selectedRule?.needsSupervisorReview && <p className="supervisor-note">该条款含浮动或指标条件，须主管最终认定。</p>}
    </section>}
  </>;
  const downloads = <section className="download-card"><div><strong>确认无误后下载</strong><p>{documentData ? `${documentData.rule.clause} · ${documentData.pricing.unit} · ${documentData.quantityNumber} × ${documentData.pricing.unitPrice}元` : '请先完成 AI 分析或手动选择考核依据。'}</p></div><div className="download-actions"><button onClick={() => exportFile('word')} disabled={exportState === 'loading'}><DocumentArrowDownIcon />Word</button><button className="secondary" onClick={() => exportFile('pdf')} disabled={exportState === 'loading'}><PrinterIcon />PDF</button></div>{exportMessage && <p className={`download-state ${exportState}`}>{exportMessage}</p>}</section>;

  return <div className="app-shell"><header className="topbar"><div className="brand"><span className="brand-mark">邮</span><div><small>中国邮政<br />CHINA POST</small><strong>邮件处理中心考核助手</strong></div><em>正式版</em></div><div className="top-actions"><button onClick={() => setTab('ask')}><BookOpenIcon />制度问答</button><span className="user-dot">张</span><span className="desktop-only">当前用户</span></div></header>
    <main>{tab === 'create' ? <section className="workbench">
      <article className="input-pane"><div className="pane-heading"><div><p>开具考核通知单</p><h1>填写考核信息</h1></div><span>本地草稿已开启</span><button className="clear-draft" onClick={() => { if (window.confirm('确定清除这台电脑上的全部考核草稿吗？')) { clearDraft(); setForm(initialForm); setErrors({}); setStep(1); } }}>清除本机草稿</button></div>
        {ruleError ? <div className="error-banner"><ExclamationTriangleIcon />{ruleError}<button onClick={() => { setRuleError(''); loadRules().then(setRules).catch((error: Error) => setRuleError(error.message)); }}>重试</button></div> : <>
          <div className="mobile-steps"><span className={step >= 1 ? 'active' : ''}>1 基本信息</span><span className={step >= 2 ? 'active' : ''}>2 AI 分析</span><span className={step >= 3 ? 'active' : ''}>3 下载</span></div>
          <div className="desktop-flow">{basics}<hr />{assessment}{downloads}</div>
          <div className="mobile-flow">{step === 1 && basics}{step === 2 && assessment}{step === 3 && <>{downloads}<div className="mobile-preview"><PreviewPane documentData={documentData} previewZoom={previewZoom} onZoomChange={setPreviewZoom} previewRef={previewRef} /></div></>}<div className="mobile-actions">{step > 1 && <button onClick={() => setStep((value) => value - 1)}><ChevronLeftIcon />上一步</button>}{step < 3 && <button className="primary" onClick={next}>下一步<ChevronRightIcon /></button>}</div></div>
        </>}
      </article><aside className="preview-pane"><PreviewPane documentData={documentData} previewZoom={previewZoom} onZoomChange={setPreviewZoom} previewRef={previewRef} /></aside>
    </section> : <section className="ask-workbench"><article className="ask-pane"><p className="section-kicker">制度查询助手</p><h1>用日常话问制度</h1><p className="subtle">例如“卸完车忘记在 PDA 点完成怎么办？”AI 会依据正式条款告诉您能不能做、应如何处理及可能后果。</p><label className="question-input"><span>请输入您的问题</span><div><MagnifyingGlassIcon /><textarea maxLength={160} value={question} onChange={(event) => { setQuestion(event.target.value); setPolicyAnswer(null); setPolicyState('idle'); setPolicyMessage(''); }} placeholder="例如：卸完车后忘了在 PDA 点完成，会有什么后果？" /></div></label><button className="ai-button policy-query-button" onClick={runPolicyQuery} disabled={policyState === 'loading'}><SparklesIcon />{policyState === 'loading' ? 'AI 正在查询制度…' : 'AI 查询制度依据'}</button>{policyMessage && <p className={`policy-message ${policyState}`}>{policyMessage}</p>}{policyAnswer && <div className="answer-card"><p>{matched.length ? 'AI 已匹配正式制度依据' : '未找到可确认的制度依据'}</p><h2>{policyAnswer.conclusion}</h2><dl><div><dt>建议怎么做</dt><dd>{policyAnswer.recommendedAction}</dd></div><div><dt>后果 / 考核标准</dt><dd>{policyAnswer.consequence}</dd></div></dl>{policyAnswer.needsSupervisorReview && <span>此情形仍需主管结合现场情况最终认定。</span>}</div>}</article><aside className="evidence-pane"><div className="evidence-heading"><BookOpenIcon />条例依据</div>{matched.length ? matched.map((rule) => <article className="rule-card" key={rule.id}><p>{rule.stage}</p><h2>{rule.clause}</h2><h3>{rule.name}</h3><span>{rule.original}</span><strong>{rule.pricingOptions.map((item) => item.unitPrice === null ? '主管认定' : `${item.unitPrice}元/${item.unit}`).join('；')}</strong></article>) : <p className="empty-evidence">输入问题后点击“AI 查询制度依据”，命中条款会完整显示在这里。</p>}</aside></section>}</main>
  </div>;

}

createRoot(document.getElementById('root')!).render(<App />);
