import { describe, expect, it } from 'vitest';
import { createRequestGate } from './requestGate';

describe('会话和请求隔离', () => {
  it('退出或换账号使旧请求失效', () => {
    const gate = createRequestGate();
    const old = gate.capture();
    expect(gate.isCurrent(old)).toBe(true);
    gate.invalidate();
    expect(gate.isCurrent(old)).toBe(false);
    expect(gate.isCurrent(gate.capture())).toBe(true);
  });
  it('只允许最新列表请求和最新表单写入', () => {
    const gate = createRequestGate();
    const slow = gate.invalidate();
    const latest = gate.invalidate();
    expect(gate.isCurrent(slow)).toBe(false);
    expect(gate.isCurrent(latest)).toBe(true);
  });
});
