import type { DocumentKind, QuickRecord, RecordStatus } from './types';

// 小程序部分机型的 JS 引擎缺少完整 Intl，这里的格式化都不依赖 Intl / toLocaleString。

const DIGITS = '零壹贰叁肆伍陆柒捌玖';
const UNITS = ['', '拾', '佰', '仟'];
const BIG_UNITS = ['', '万', '亿', '兆'];

function fourToChinese(value: number): string {
  let result = '';
  let zero = false;
  for (let position = 3; position >= 0; position -= 1) {
    const digit = Math.floor(value / 10 ** position) % 10;
    if (digit) {
      if (zero) result += '零';
      result += `${DIGITS[digit]}${UNITS[position]}`;
      zero = false;
    } else if (result) zero = true;
  }
  return result.replace(/零+$/, '');
}

/** 人民币大写，规则与后端 money.amount_to_chinese 一致。 */
export function amountToChinese(value: string | number): string {
  const raw = String(value).trim();
  if (!/^\d+(\.\d{0,2})?$/.test(raw)) return '金额格式不正确';
  const [wholeText, fractionalText = ''] = raw.split('.');
  let whole = Number(wholeText);
  const fraction = Number(fractionalText.padEnd(2, '0'));
  let integerText = '零';
  if (whole) {
    const groups: number[] = [];
    while (whole) { groups.push(whole % 10000); whole = Math.floor(whole / 10000); }
    const parts: string[] = [];
    let pendingZero = false;
    for (let index = groups.length - 1; index >= 0; index -= 1) {
      const group = groups[index];
      if (!group) { pendingZero = parts.length > 0; continue; }
      if (parts.length && (pendingZero || group < 1000)) parts.push('零');
      parts.push(`${fourToChinese(group)}${BIG_UNITS[index]}`);
      pendingZero = false;
    }
    integerText = parts.join('');
  }
  if (!fraction) return `${integerText}元整`;
  const jiao = Math.floor(fraction / 10);
  const fen = fraction % 10;
  return `${integerText}元${jiao ? `${DIGITS[jiao]}角` : (wholeText !== '0' && fen ? '零' : '')}${fen ? `${DIGITS[fen]}分` : ''}`;
}

/** 1234.5 -> "1,234.50"；非法值显示 "0.00"。 */
export function formatMoney(value: string | number): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return '0.00';
  const [integer, fraction] = Math.abs(amount).toFixed(2).split('.');
  return `${amount < 0 ? '-' : ''}${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction}`;
}

/** 北京时间的当天日期（YYYY-MM-DD），不依赖设备时区设置。 */
export function beijingToday(now: number = Date.now()): string {
  return new Date(now + 8 * 3600 * 1000).toISOString().slice(0, 10);
}

/** "2026-11-23" -> "2026年11月23日"；无法识别时原样返回。 */
export function formatCnDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return match ? `${Number(match[1])}年${Number(match[2])}月${Number(match[3])}日` : value;
}

export function statusLabel(status: RecordStatus | string): string {
  return ({ draft: '未生成', effective: '已生成', voided: '已作废' } as Record<string, string>)[status] || status;
}

/** 复制到群里的纯文字版本。 */
export function shareText(record: QuickRecord): string {
  return [
    record.assessment_no || `草稿 #${record.id}`,
    `${record.team} ${record.inspector_name}`,
    `${record.incident_date} ${record.shift}`,
    record.assessment_unit_name_snapshot,
    record.assessment_content,
    `数量：${record.quantity}；考核金额：${formatMoney(record.penalty_amount)}元（${record.penalty_amount_cn}）`,
  ].join('\n');
}

const EXTENSIONS: Record<DocumentKind, string> = { word: 'docx', pdf: 'pdf', png: 'png' };

/** 下载/转发时使用的文件名，去掉文件系统不允许的字符。 */
export function documentFileName(record: QuickRecord, kind: DocumentKind): string {
  const stem = (record.assessment_no || `考核单-${record.id}`).replace(/[\\/:*?"<>|\s]+/g, '-');
  return `${stem}.${EXTENSIONS[kind]}`;
}

/** 合并本机记录：按 id 去重、保留更新时间较新的一份，按 id 倒序。 */
export function mergeRecent(current: QuickRecord[], incoming: QuickRecord[], limit = 50): QuickRecord[] {
  const byId: Record<number, QuickRecord> = {};
  for (const item of current.concat(incoming)) {
    const previous = byId[item.id];
    if (!previous || Date.parse(item.updated_at) > Date.parse(previous.updated_at)) byId[item.id] = item;
  }
  return Object.keys(byId).map((key) => byId[Number(key)]).sort((a, b) => b.id - a.id).slice(0, limit);
}
