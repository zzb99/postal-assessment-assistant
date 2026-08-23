import { amountToChinese } from './money';

export const amountInChinese = (amount: number) => amountToChinese(Math.max(0, amount));

export const formatDate = (value: string) => {
  const [year, month, day] = value.split('-').map(Number);
  return year && month && day ? `${year}年${month}月${day}日` : '';
};
