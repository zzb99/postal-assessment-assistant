import type { CSSProperties } from 'react';

export type TemplateField = 'company' | 'noticeSummary' | 'amount' | 'inspector' | 'date';

export type TemplateSlot = {
  top: number;
  left: number;
  width?: number;
  height?: number;
  fontSizePt: number;
  lineHeight?: number;
  wordRow?: number;
};

// These values are measured from assessment-notice-template.png (2382 × 3368).
// Word and PDF use the same slots; the browser preview reads them as percentages.
export const TEMPLATE_SLOTS: Record<TemplateField, TemplateSlot> = {
  company: { top: 18.8, left: 28.7, width: 59.2, height: 2.2, fontSizePt: 16, wordRow: 0 },
  noticeSummary: { top: 24.1, left: 28.7, width: 59.2, height: 38.8, fontSizePt: 16, lineHeight: 1.28, wordRow: 1 },
  amount: { top: 63.05, left: 28.7, width: 59.2, height: 2.35, fontSizePt: 16, wordRow: 2 },
  inspector: { top: 83.15, left: 22, width: 23, height: 2.1, fontSizePt: 18 },
  date: { top: 83.15, left: 61, width: 28, height: 2.1, fontSizePt: 18 },
};

export const templateFieldStyle = (field: TemplateField): CSSProperties => {
  const slot = TEMPLATE_SLOTS[field];
  return {
    top: `${slot.top}%`, left: `${slot.left}%`, width: slot.width ? `${slot.width}%` : undefined,
    height: slot.height ? `${slot.height}%` : undefined,
    // The source template is 2382px wide at 288dpi: 1pt = 4px.
    '--template-font-size': `${(slot.fontSizePt * 4 / 2382 * 100).toFixed(3)}cqw`,
    '--template-line-height': String(slot.lineHeight ?? 1.2),
  } as CSSProperties;
};
