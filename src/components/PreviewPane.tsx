import { DocumentTextIcon, MinusIcon, PlusIcon } from '@heroicons/react/24/outline';
import type { CSSProperties, RefObject } from 'react';
import type { DocumentData } from '../types';
import { NoticePreview } from './NoticePreview';

export function PreviewPane({ documentData, previewZoom, onZoomChange, previewRef }: { documentData?: DocumentData; previewZoom: number; onZoomChange: (zoom: number) => void; previewRef: RefObject<HTMLElement | null> }) {
  return <div className="preview-shell"><div className="preview-toolbar"><span><DocumentTextIcon />正式通知单预览</span><div><button aria-label="缩小" onClick={() => onZoomChange(Math.max(80, previewZoom - 10))}><MinusIcon /></button><button className="zoom-value" aria-label="适合页面" onClick={() => onZoomChange(100)}>{previewZoom}%</button><button aria-label="放大" onClick={() => onZoomChange(Math.min(120, previewZoom + 10))}><PlusIcon /></button></div></div><div className="paper-stage"><div className="paper-zoom" style={{ zoom: previewZoom / 100 } as CSSProperties}><NoticePreview data={documentData} previewRef={previewRef} /></div></div></div>;
}
