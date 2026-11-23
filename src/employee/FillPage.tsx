import { useEffect, useState, useSyncExternalStore } from 'react';
import type { ChangeEvent, ReactNode } from 'react';
import type { FillController } from '@shared/controller';
import type { EditableField } from '@shared/fill';
import { rememberRecords } from './platform';

function CardHead({ step, title, tip, action }: { step: number; title: string; tip?: string; action?: ReactNode }) {
  return (
    <div className="emp-card-head">
      <span className="emp-step" aria-hidden="true">{step}</span>
      <h2>{title}</h2>
      {tip && <small>{tip}</small>}
      {action}
    </div>
  );
}

/** 职工填报页：所有业务状态来自共用控制器，与小程序填报页的结构一一对应。 */
export function FillPage({ controller }: { controller: FillController }) {
  const { state, view, config, storageOk } = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const [quantityAnswer, setQuantityAnswer] = useState('');
  const [rulesOpen, setRulesOpen] = useState(view.rulesOpen);
  const [seenComposition, setSeenComposition] = useState(state.composition);
  if (seenComposition !== state.composition) {
    // 每次拿到新的 AI 结果时，按结果决定制度依据是否默认展开。
    setSeenComposition(state.composition);
    setRulesOpen(view.rulesOpen);
  }

  useEffect(() => {
    if (!controller.getSnapshot().config) void controller.loadConfig();
  }, [controller]);

  const form = state.form;
  const locked = state.aiPending || state.submitting;
  const bind = (key: EditableField) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => controller.setField(key, event.target.value);

  const generate = async () => {
    const record = await controller.submit();
    if (record) {
      rememberRecords([record]);
      window.location.hash = `#/result/${record.id}?fresh`;
    }
  };

  const answerQuantity = () => {
    if (!view.question) return;
    void controller.answer(view.question, Number(quantityAnswer));
    setQuantityAnswer('');
  };

  const modeLabel = state.mode === 'ai' ? (form.assessment_content ? '手动调整' : '不用AI，手动填') : '返回AI整理';

  return (
    <div className="emp-page">
      <div className="emp-hero">
        <h1>填写考核单</h1>
        <p>描述现场问题，核对后生成，直接发到微信群</p>
      </div>

      {state.error && !config && (
        <div className="emp-alert emp-alert-error" role="alert">
          {state.error}
          <button type="button" className="emp-link" onClick={() => void controller.loadConfig()}>重试</button>
        </div>
      )}
      {!storageOk && <div className="emp-alert emp-alert-warn">浏览器未允许保存，关闭页面前请先复制正文。</div>}

      <section className="emp-card">
        <CardHead step={1} title="检查人" tip="自动记住，下次不用再填" />
        <div className="emp-row">
          <label className="emp-field">
            <span className="emp-label">班组</span>
            <input value={form.team} onChange={bind('team')} maxLength={32} placeholder="例如 二班" disabled={locked} autoComplete="organization" />
          </label>
          <label className="emp-field">
            <span className="emp-label">姓名</span>
            <input value={form.inspector_name} onChange={bind('inspector_name')} maxLength={100} placeholder="你的姓名" disabled={locked} autoComplete="name" />
          </label>
        </div>
      </section>

      <section className="emp-card">
        <CardHead step={2} title="检查信息" />
        <label className="emp-field">
          <span className="emp-label">检查日期</span>
          <input type="date" value={form.incident_date} onChange={bind('incident_date')} disabled={locked} />
        </label>
        <div className="emp-field">
          <span className="emp-label" id="emp-shift">班次</span>
          <div className="emp-segmented" role="radiogroup" aria-labelledby="emp-shift">
            {view.shifts.map((shift) => (
              <button type="button" key={shift} role="radio" aria-checked={form.shift === shift} className={form.shift === shift ? 'on' : ''} disabled={locked} onClick={() => controller.setField('shift', shift)}>{shift}</button>
            ))}
          </div>
        </div>
        <label className="emp-field">
          <span className="emp-label">被考核公司</span>
          <select value={form.unit} onChange={bind('unit')} disabled={locked || !config}>
            <option value="">{config ? '请选择公司' : '正在加载…'}</option>
            {(config?.units || []).map((unit) => <option key={unit.id} value={String(unit.id)}>{unit.name}</option>)}
          </select>
        </label>
      </section>

      <section className="emp-card">
        <CardHead step={3} title={state.mode === 'ai' ? '描述现场问题' : '手动填写'}
          action={view.aiEnabled && !locked ? <button type="button" className="emp-link emp-head-link" onClick={() => controller.setMode(state.mode === 'ai' ? 'manual' : 'ai')}>{modeLabel}</button> : null} />
        {state.mode === 'ai' ? (
          <>
            <label className="emp-field">
              <span className="emp-sr">现场问题</span>
              <textarea value={form.facts} onChange={bind('facts')} maxLength={1000} rows={4} disabled={locked}
                placeholder="例如：现场抽烟；小件机发现遗留1件；卸车完毕后发现遗留邮件。只写事实，不用写条款。" />
            </label>
            <button type="button" className="emp-btn emp-btn-primary emp-btn-block" disabled={!view.canCompose} onClick={() => void controller.compose()}>
              {state.aiPending ? '正在处理…' : 'AI 智能整理'}
            </button>
            {state.message && <p className="emp-note" role="status">{state.message}</p>}
            {view.notice && <details className="emp-note emp-note-muted"><summary>正文整理说明</summary><p>{view.notice}</p></details>}

            {view.question && (
              <div className="emp-question">
                <strong>{view.question.question}</strong>
                {view.question.kind === 'boolean' ? (
                  <div className="emp-row">
                    <button type="button" className="emp-btn emp-btn-primary" disabled={state.aiPending} onClick={() => void controller.answer(view.question!, true)}>是，确认属实</button>
                    <button type="button" className="emp-btn" disabled={state.aiPending} onClick={() => void controller.answer(view.question!, false)}>否</button>
                  </div>
                ) : (
                  <div className="emp-row emp-row-center">
                    <label className="emp-field">
                      <span className="emp-sr">计费数量</span>
                      <input type="number" inputMode="numeric" min={1} max={100000} step={1} value={quantityAnswer} onChange={(event) => setQuantityAnswer(event.target.value)} placeholder="计费数量" />
                    </label>
                    <button type="button" className="emp-btn emp-btn-primary" disabled={state.aiPending || !quantityAnswer} onClick={answerQuantity}>确认数量</button>
                  </div>
                )}
                <small>请按现场实际情况选择，系统据此核算金额。</small>
              </div>
            )}

            {view.rulesVisible && (
              <div className="emp-rules">
                <button type="button" className="emp-rules-head" aria-expanded={rulesOpen} onClick={() => setRulesOpen(!rulesOpen)}>
                  <span>{view.rulesTitle}</span><span>{rulesOpen ? '收起' : '展开'}</span>
                </button>
                {rulesOpen && (
                  <>
                    {view.rules.map((rule) => (
                      <div className="emp-rule" key={rule.id}>
                        <strong>{rule.clause}{rule.current && <span className="emp-tag">当前条款</span>}</strong>
                        <p>{rule.original}</p>
                        {rule.options.map((option) => (
                          <div className="emp-option" key={option.id}>
                            <p>{option.label}</p>
                            <small>{option.automatic ? '按实际情况补全条件后计算金额' : '复杂标准需手动核定金额'}</small>
                            <button type="button" className="emp-btn emp-btn-small" disabled={state.aiPending} onClick={() => void controller.choose(rule.id, option.id)}>选择此条款</button>
                          </div>
                        ))}
                      </div>
                    ))}
                    {(view.hiddenRules > 0 || state.showAllRules) && (
                      <button type="button" className="emp-link emp-center" onClick={() => controller.toggleRules()}>
                        {state.showAllRules ? '收起其他条款' : `查看其他相关条款（${view.hiddenRules}）`}
                      </button>
                    )}
                  </>
                )}
              </div>
            )}
            {config && !view.aiEnabled && <p className="emp-hint">服务器尚未配置 AI，请改为手动填写。</p>}
          </>
        ) : (
          <p className="emp-hint">直接填写下方正文、数量和金额；正文里写的金额必须与填写金额一致。</p>
        )}
      </section>

      {view.showReview ? (
        <section className="emp-card">
          <CardHead step={4} title="核对考核单" />
          <label className="emp-field">
            <span className="emp-label">{view.contentLabel}</span>
            <textarea className={view.contentEditable ? '' : 'emp-readonly'} value={form.assessment_content} onChange={bind('assessment_content')} maxLength={600} rows={8}
              readOnly={!view.contentEditable} disabled={locked} placeholder="填写现场事实、制度依据、考核金额及整改要求。" />
            <small className="emp-counter">{view.contentCount}</small>
          </label>
          {view.amountsVisible && (
            <>
              <div className="emp-row">
                <label className="emp-field">
                  <span className="emp-label">数量</span>
                  <input className={view.amountsEditable ? '' : 'emp-readonly'} type="number" inputMode="numeric" min={1} max={100000} step={1} value={form.quantity} onChange={bind('quantity')} readOnly={!view.amountsEditable} disabled={locked} />
                </label>
                <label className="emp-field">
                  <span className="emp-label">考核金额（元）</span>
                  <input className={view.amountsEditable ? '' : 'emp-readonly'} type="number" inputMode="numeric" min={1} max={100000000} step={1} value={form.penalty_amount} onChange={bind('penalty_amount')} readOnly={!view.amountsEditable} disabled={locked} />
                </label>
              </div>
              <p className="emp-money">大写：{view.amountCn}</p>
            </>
          )}
          {view.confirmVisible && (
            <label className="emp-confirm">
              <input type="checkbox" checked={state.editConfirmed} disabled={locked} onChange={(event) => controller.confirm(event.target.checked)} />
              <span>{view.confirmText}</span>
            </label>
          )}
        </section>
      ) : (
        <section className="emp-card emp-card-empty">整理完成后，正文和金额会显示在这里。</section>
      )}

      <div className="emp-action-bar">
        {state.error && config && <p className="emp-action-error" role="alert">{state.error}</p>}
        {!state.error && view.blocker && !state.submitting && <p>{view.blocker}</p>}
        {/* 不放在 form 提交里：在输入框按回车不能误生成正式考核单。 */}
        <button type="button" className="emp-btn emp-btn-primary emp-btn-block" disabled={Boolean(view.blocker) || state.submitting} onClick={() => void generate()}>{view.submitLabel}</button>
      </div>
    </div>
  );
}
