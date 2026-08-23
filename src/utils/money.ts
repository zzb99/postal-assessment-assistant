const DIGITS = '零壹贰叁肆伍陆柒捌玖';
const UNITS = ['', '拾', '佰', '仟'];
const BIG_UNITS = ['', '万', '亿', '兆'];

function fourToChinese(value: number) {
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

export function formatMoney(value: string | number): string {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00';
}
