export function continuationRequest(token: string, answers: Record<string, boolean | number>) {
  if (!token || !Object.keys(answers).length) throw new Error('请先选择需要确认的条件。');
  for (const [key, value] of Object.entries(answers)) {
    if (key === 'billing_quantity') {
      if (!Number.isInteger(value) || Number(value) < 1 || Number(value) > 100000) throw new Error('计费数量须为1至100000的整数。');
    } else if (typeof value !== 'boolean') throw new Error('条件答案无效。');
  }
  return { path: '/ai/continue', body: { continuation_token: token, answers } };
}
