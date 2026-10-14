import type { RefObject } from 'react';
import type { DocumentData } from '../types';
import { templateFieldStyle } from '../templateLayout';

export function NoticePreview({ data, previewRef }: { data?: DocumentData; previewRef: RefObject<HTMLElement | null> }) {
  return <article className="notice-paper template-paper" ref={previewRef} aria-label="考核通知单预览">
    <img className="template-background" src="/assessment-notice-template.png" alt="空白考核通知单模板" />
    {data && <>
      <span className="template-field company-field" style={templateFieldStyle('company')}>{data.company}</span>
      <p className="template-field event-field" style={templateFieldStyle('noticeSummary')}>{data.noticeSummary}</p>
      <span className="template-field amount-field" style={templateFieldStyle('amount')}>{data.amountChinese}（大写）</span>
      <span className="template-field inspector-field" style={templateFieldStyle('inspector')}>{data.inspector}</span>
      <span className="template-field date-field" style={templateFieldStyle('date')}>{data.formattedDate}</span>
    </>}
  </article>;
}
