import { useEffect, useState } from 'react';
import { formatMoney, shareText, statusLabel } from '@shared/format';
import type { QuickRecord } from '@shared/types';
import { cachedRecord, copyText, documentFile, findRecord, inWeChat, saveFile, shareFile } from './platform';

const messageOf = (error: unknown, fallback: string) => (error instanceof Error && error.message ? error.message : fallback);

/** 生成结果与分享：图片和 PDF 先准备好，点击分享时直接调起系统分享，避免点击授权过期。 */
export function ResultPage({ id, fresh }: { id: number; fresh: boolean }) {
  const [record, setRecord] = useState<QuickRecord | null>(() => cachedRecord(id));
  const [loading, setLoading] = useState(() => !cachedRecord(id));
  const [error, setError] = useState('');
  const [image, setImage] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState('');
  const [pdf, setPdf] = useState<File | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [hint, setHint] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    const known = cachedRecord(id);
    setRecord(known);
    setLoading(!known);
    setError('');
    if (!known) {
      findRecord(id)
        .then((found) => { if (!alive) return; setRecord(found); if (!found) setError('本机找不到这张考核单。'); })
        .catch((cause) => { if (alive) setError(messageOf(cause, '读取失败，请稍后重试。')); })
        .finally(() => { if (alive) setLoading(false); });
    }
    return () => { alive = false; };
  }, [id]);

  useEffect(() => {
    if (!record || record.status !== 'effective') return undefined;
    let alive = true;
    let url = '';
    setPreparing(true);
    setHint('正在准备文书图片和 PDF…');
    const png = documentFile(record, 'png').then((file) => {
      if (!alive) return;
      url = URL.createObjectURL(file);
      setImage(file);
      setImageUrl(url);
    });
    const pdfReady = documentFile(record, 'pdf').then((file) => { if (alive) setPdf(file); });
    Promise.all([png, pdfReady])
      .then(() => { if (alive) setHint(inWeChat() ? '在微信里请长按下方图片，选择「发送给朋友」发到群里。' : ''); })
      .catch((cause) => { if (alive) setHint(`${messageOf(cause, '文书读取失败')}，可点「重新加载文书」再试。`); })
      .finally(() => { if (alive) setPreparing(false); });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [record, attempt]);

  if (loading) return <p className="emp-empty">正在读取考核单…</p>;
  if (error || !record) {
    return (
      <div className="emp-card">
        <div className="emp-alert emp-alert-error">{error || '本机找不到这张考核单。'}</div>
        <a className="emp-btn emp-btn-block" href="#/">返回填写</a>
      </div>
    );
  }

  const effective = record.status === 'effective';

  const share = async (file: File | null, kind: '图片' | 'PDF') => {
    if (!file) return;
    try {
      const result = await shareFile(file);
      if (result === 'unsupported') setHint(inWeChat() ? '微信内置浏览器不能直接分享文件：请长按图片发送给朋友，或改用小程序。' : `当前浏览器不能直接分享文件，请点「保存${kind}」后再发到微信群。`);
      else if (result === 'shared') setHint('已打开系统分享，请选择微信并发到对应的群。');
      else setHint('已取消分享，文件仍在，可以重新分享。');
    } catch (cause) {
      setHint(`无法直接分享：${messageOf(cause, `请先保存${kind}，再发群。`)}`);
    }
  };

  const downloadWord = async () => {
    try { saveFile(await documentFile(record, 'word')); } catch (cause) { setHint(messageOf(cause, 'Word 下载失败，请重试。')); }
  };

  const copy = async () => {
    setHint((await copyText(shareText(record))) ? '文字已复制，可粘贴到群里。' : '复制失败，请保存图片或下载文件。');
  };

  return (
    <div className="emp-page">
      <div className={`emp-result-hero${effective ? '' : ' muted'}`}>
        <div className="emp-result-icon" aria-hidden="true">{effective ? '✓' : '!'}</div>
        <h1>{effective ? (fresh ? '考核单已生成' : '正式考核单') : `考核单${statusLabel(record.status)}`}</h1>
        <p className="emp-result-no">{record.assessment_no || '未生成编号'}</p>
        <p>{record.team} · {record.inspector_name} · {record.incident_date} {record.shift}</p>
      </div>

      {effective ? (
        <section className="emp-card">
          <div className="emp-row">
            <button type="button" className="emp-btn emp-btn-primary" disabled={!image} onClick={() => void share(image, '图片')}>发到微信群</button>
            <button type="button" className="emp-btn" disabled={!pdf} onClick={() => void share(pdf, 'PDF')}>分享 PDF 文件</button>
          </div>
          {hint && <p className="emp-note emp-note-muted" role="status">{hint}</p>}
          {!preparing && (!image || !pdf) && <button type="button" className="emp-btn emp-btn-block" onClick={() => setAttempt((value) => value + 1)}>重新加载文书</button>}
          <div className="emp-document">
            {imageUrl ? <img src={imageUrl} alt={`${record.assessment_no}正式考核单，可长按保存或发送`} /> : <p>{preparing ? '正在生成文书图片…' : '文书图片暂不可用'}</p>}
          </div>
          <div className="emp-row emp-more">
            <button type="button" className="emp-btn" disabled={!image} onClick={() => image && saveFile(image)}>保存图片</button>
            <button type="button" className="emp-btn" disabled={!pdf} onClick={() => pdf && saveFile(pdf)}>下载PDF</button>
            <button type="button" className="emp-btn" onClick={() => void downloadWord()}>下载Word</button>
          </div>
        </section>
      ) : (
        <section className="emp-card">
          <div className="emp-alert emp-alert-warn">这张考核单{statusLabel(record.status)}，不能分享正式文书。</div>
          {record.void_reason && <p className="emp-hint">作废原因：{record.void_reason}</p>}
        </section>
      )}

      <section className="emp-card">
        <div className="emp-card-head"><h2>考核内容</h2><button type="button" className="emp-link emp-head-link" onClick={() => void copy()}>复制文字</button></div>
        <dl className="emp-kv">
          <div><dt>被考核公司</dt><dd>{record.assessment_unit_name_snapshot}</dd></div>
          <div><dt>数量</dt><dd>{record.quantity}</dd></div>
          <div><dt>考核金额</dt><dd>¥{formatMoney(record.penalty_amount)}（{record.penalty_amount_cn}）</dd></div>
        </dl>
        <p className="emp-content">{record.assessment_content}</p>
      </section>

      <a className="emp-btn emp-btn-primary emp-btn-block emp-next" href="#/">再填一张</a>
    </div>
  );
}
