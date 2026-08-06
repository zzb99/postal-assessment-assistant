export const amountInChinese = (amount: number) => {
  if (!Number.isFinite(amount) || amount <= 0) return '零元整';
  const digits = '零壹贰叁肆伍陆柒捌玖';
  const units = ['', '拾', '佰', '仟'];
  const bigUnits = ['', '万', '亿'];
  let remaining = Math.round(amount);
  let group = 0;
  let output = '';
  while (remaining > 0) {
    let part = remaining % 10000;
    let piece = '';
    let position = 0;
    let needsZero = false;
    while (part > 0) {
      const digit = part % 10;
      if (digit === 0) needsZero = piece.length > 0;
      else { piece = `${digits[digit]}${units[position]}${needsZero ? '零' : ''}${piece}`; needsZero = false; }
      part = Math.floor(part / 10); position += 1;
    }
    if (piece) output = `${piece}${bigUnits[group]}${output && part < 1000 ? '零' : ''}${output}`;
    remaining = Math.floor(remaining / 10000); group += 1;
  }
  return `${output.replace(/零+/g, '零').replace(/零$/g, '')}元整`;
};

export const formatDate = (value: string) => {
  const [year, month, day] = value.split('-').map(Number);
  return year && month && day ? `${year}年${month}月${day}日` : '';
};
