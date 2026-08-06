import PizZip from 'pizzip';
import { PDFDocument } from 'pdf-lib';
import { saveAs } from 'file-saver';
import type { AssessmentForm, AssessmentRule, DocumentData, PricingOption } from '../types';
import { amountInChinese, formatDate } from '../utils/currency';
import { buildNoticeSummary } from '../utils/noticeSummary';
import { TEMPLATE_SLOTS, type TemplateField } from '../templateLayout';

export const fileStem = (data: DocumentData) => `${data.noticeNo}-${data.company}-${data.date}-考核通知单`.replace(/[\\/:*?"<>|]/g, '-');

export function buildDocumentData(form: AssessmentForm, rule: AssessmentRule, pricing: PricingOption): DocumentData {
  const quantityNumber = Number(form.quantity);
  const amount = quantityNumber * (pricing.unitPrice ?? 0);
  const formattedDate = formatDate(form.date);
  const noticeSummary = buildNoticeSummary(form, rule, pricing, amount);
  return { ...form, rule, pricing, quantityNumber, amount, amountChinese: amountInChinese(amount), formattedDate, noticeSummary, itemText: noticeSummary };
}

async function fetchTemplate(fetcher: typeof fetch = fetch): Promise<ArrayBuffer> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const response = await fetcher('/assessment-notice-template.docx', { cache: 'no-store' });
      if (!response.ok) throw new Error(`模板请求失败（${response.status}）`);
      return await response.arrayBuffer();
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(`Word 模板加载失败，请检查网络或点击重试。${lastError instanceof Error ? ` ${lastError.message}` : ''}`);
}

async function fetchPdfTemplate(fetcher: typeof fetch = fetch): Promise<ArrayBuffer> {
  const response = await fetcher('/assessment-notice-template.pdf', { cache: 'no-store' });
  if (!response.ok) throw new Error(`PDF 模板请求失败（${response.status}）`);
  return response.arrayBuffer();
}

type WordTextStyle = { halfPoints: number };

const wordNamespace = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';

const isWordElement = (node: Element, name: string) => node.namespaceURI === wordNamespace && node.localName === name;

function createWordElement(xml: XMLDocument, name: string) {
  return xml.createElementNS(wordNamespace, `w:${name}`);
}

function applyWordStyle(xml: XMLDocument, run: Element, style: WordTextStyle) {
  const properties = createWordElement(xml, 'rPr');
  const fonts = createWordElement(xml, 'rFonts');
  fonts.setAttribute('w:ascii', 'SimSun');
  fonts.setAttribute('w:hAnsi', 'SimSun');
  fonts.setAttribute('w:eastAsia', 'SimSun');
  properties.appendChild(fonts);
  for (const name of ['sz', 'szCs']) {
    const size = createWordElement(xml, name);
    size.setAttribute('w:val', String(style.halfPoints));
    properties.appendChild(size);
  }
  run.appendChild(properties);
}

function editableParagraph(xml: XMLDocument, container: Element) {
  if (isWordElement(container, 'p')) return container;
  const existing = Array.from(container.getElementsByTagNameNS(wordNamespace, 'p'))[0];
  if (existing) return existing;
  const paragraph = createWordElement(xml, 'p');
  container.appendChild(paragraph);
  return paragraph;
}

/**
 * Writes into a known template slot. Empty value cells are valid: the supplied
 * template deliberately contains only an empty w:p there, not a w:t node.
 */
function setTextInContainer(xml: XMLDocument, container: Element, value: string, style: WordTextStyle) {
  const paragraph = editableParagraph(xml, container);
  Array.from(paragraph.children)
    .filter((node) => isWordElement(node, 'r') || isWordElement(node, 'hyperlink'))
    .forEach((node) => paragraph.removeChild(node));
  const run = createWordElement(xml, 'r');
  applyWordStyle(xml, run, style);
  value.split('\n').forEach((line, index) => {
    if (index) run.appendChild(createWordElement(xml, 'br'));
    const text = createWordElement(xml, 't');
    text.setAttribute('xml:space', 'preserve');
    text.textContent = line;
    run.appendChild(text);
  });
  paragraph.appendChild(run);
}

function templateValueCell(rows: Element[], rowIndex: number) {
  const cells = Array.from(rows[rowIndex]?.children ?? []).filter((node): node is Element => node instanceof Element && isWordElement(node, 'tc'));
  const valueCell = cells[1];
  if (!valueCell) throw new Error(`Word 模板第 ${rowIndex + 1} 行缺少填写单元格。`);
  return valueCell;
}

function setCellVerticalAlign(xml: XMLDocument, cell: Element, value: 'center') {
  let properties = Array.from(cell.children).find((node) => isWordElement(node, 'tcPr'));
  if (!properties) { properties = createWordElement(xml, 'tcPr'); cell.insertBefore(properties, cell.firstChild); }
  let alignment = Array.from(properties.children).find((node) => isWordElement(node, 'vAlign'));
  if (!alignment) { alignment = createWordElement(xml, 'vAlign'); properties.appendChild(alignment); }
  alignment.setAttribute('w:val', value);
}

export async function exportWord(data: DocumentData, fetcher: typeof fetch = fetch) {
  const template = await fetchTemplate(fetcher);
  const zip = new PizZip(template);
  const documentXml = zip.file('word/document.xml');
  if (!documentXml) throw new Error('Word 模板内容损坏。');
  const xml = new DOMParser().parseFromString(documentXml.asText(), 'application/xml');
  if (xml.getElementsByTagName('parsererror')[0]) throw new Error('Word 模板解析失败。');
  const table = xml.getElementsByTagNameNS(wordNamespace, 'tbl')[0];
  if (!table) throw new Error('Word 模板表格缺失。');
  const rows = Array.from(table.children).filter((node): node is Element => node instanceof Element && isWordElement(node, 'tr'));
  if (rows.length < 3) throw new Error('Word 模板字段不完整。');

  // Fixed slots from the uploaded blank template; no table or layout is rebuilt.
  // The blank value cells in the uploaded template carry 16pt paragraph styles
  // (w:sz=32). Match them instead of using the 18pt label style.
  const fillCell = (field: TemplateField, value: string) => {
    const slot = TEMPLATE_SLOTS[field];
    if (slot.wordRow === undefined) throw new Error(`Word 模板字段配置缺失：${field}`);
    const cell = templateValueCell(rows, slot.wordRow);
    setTextInContainer(xml, cell, value, { halfPoints: slot.fontSizePt * 2 });
    return cell;
  };
  fillCell('company', data.company);
  setCellVerticalAlign(xml, fillCell('noticeSummary', data.noticeSummary), 'center');
  fillCell('amount', `${data.amountChinese}（大写）`);

  const body = xml.getElementsByTagNameNS(wordNamespace, 'body')[0];
  const signatureParagraph = body && Array.from(body.getElementsByTagNameNS(wordNamespace, 'p'))
    .find((paragraph) => paragraph.textContent?.includes('检查人'));
  if (!signatureParagraph) throw new Error('Word 模板缺少“检查人/填报日期”填写位置。');
  setTextInContainer(xml, signatureParagraph, `检查人：${data.inspector}    填报日期：${data.formattedDate}`, { halfPoints: 36 });

  zip.file('word/document.xml', new XMLSerializer().serializeToString(xml));
  saveAs(zip.generate({ type: 'blob', compression: 'DEFLATE' }), `${fileStem(data)}.docx`);
}

const PDF_TEMPLATE_WIDTH = 2382;
const PDF_TEMPLATE_HEIGHT = 3368;

function drawText(ctx: CanvasRenderingContext2D, field: TemplateField, value: string) {
  const slot = TEMPLATE_SLOTS[field];
  const x = PDF_TEMPLATE_WIDTH * slot.left / 100;
  const y = PDF_TEMPLATE_HEIGHT * slot.top / 100;
  const fontSize = slot.fontSizePt * 4;
  ctx.font = `${fontSize}px SimSun, Songti SC, serif`;
  ctx.fillStyle = '#111';
  ctx.textBaseline = 'top';
  if (!slot.width) { ctx.fillText(value, x, y); return; }
  const maxWidth = PDF_TEMPLATE_WIDTH * slot.width / 100;
  const lineHeight = fontSize * (slot.lineHeight ?? 1.2);
  const lines: string[] = [];
  for (const paragraph of value.split('\n')) {
    if (!paragraph) { lines.push(''); continue; }
    let line = '';
    for (const character of paragraph) {
      if (ctx.measureText(line + character).width > maxWidth && line) {
        lines.push(line); line = character;
      } else line += character;
    }
    if (line) lines.push(line);
  }
  const areaHeight = slot.height ? PDF_TEMPLATE_HEIGHT * slot.height / 100 : 0;
  if (slot.height && lines.length * lineHeight > areaHeight) throw new Error('考核事项超过原始模板填写区域，请压缩事实经过后再生成。');
  let cursorY = y + (slot.height ? Math.max(0, (areaHeight - lines.length * lineHeight) / 2) : 0);
  for (const line of lines) {
    if (line) ctx.fillText(line, x, cursorY);
    cursorY += lineHeight;
  }
}

function createPdfOverlay(data: DocumentData) {
  const canvas = document.createElement('canvas');
  canvas.width = PDF_TEMPLATE_WIDTH;
  canvas.height = PDF_TEMPLATE_HEIGHT;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('PDF 文字图层创建失败。');
  drawText(ctx, 'company', data.company);
  drawText(ctx, 'noticeSummary', data.noticeSummary);
  drawText(ctx, 'amount', `${data.amountChinese}（大写）`);
  drawText(ctx, 'inspector', data.inspector);
  drawText(ctx, 'date', data.formattedDate);
  return canvas.toDataURL('image/png');
}

export async function exportPdf(data: DocumentData, fetcher: typeof fetch = fetch) {
  const pdf = await PDFDocument.load(await fetchPdfTemplate(fetcher));
  const page = pdf.getPage(0);
  const overlay = await pdf.embedPng(createPdfOverlay(data));
  const { width, height } = page.getSize();
  page.drawImage(overlay, { x: 0, y: 0, width, height });
  const bytes = await pdf.save();
  saveAs(new Blob([bytes.buffer as ArrayBuffer], { type: 'application/pdf' }), `${fileStem(data)}.pdf`);
}

export { fetchTemplate };
