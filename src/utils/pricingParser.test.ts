import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

function invoke(action: string, value: unknown) {
  const module = new URL(`file:///${resolve('scripts/pricing-parser.mjs').replaceAll('\\', '/')}`).href;
  const source = `import * as p from ${JSON.stringify(module)}; import {readFileSync} from 'node:fs'; console.log(JSON.stringify(p[${JSON.stringify(action)}](...JSON.parse(readFileSync(0,'utf8')))));`;
  return JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', source], { encoding: 'utf8', input: JSON.stringify(value), stdio: ['pipe', 'pipe', 'pipe'] }));
}

describe('conservative original-text pricing parser', () => {
  it.each([
    ['未执行，每次考核100元。', 'per_event', '次', 100],
    ['每人次考核50元。', 'per_event', '人次', 50],
    ['每车次考核200元。', 'per_vehicle', '车次', 200],
    ['每袋考核20元。', 'per_bag', '袋', 20],
    ['每袋（件）考核20元。', 'per_piece', '袋件', 20],
    ['考核100元/件。', 'per_piece', '件', 100],
    ['每小时考核500元。', 'per_hour', '小时', 500],
    ['一经发现考核50000元。', 'fixed', '事项', 50000],
    ['考核100-200元。', 'range', '待核定', null],
  ])('classifies %s without substring unit confusion', (text, billingType, unit, unitPrice) => {
    const option = invoke('parsePricingOptions', [text])[0];
    expect(option).toMatchObject({ billingType, unit, unitPrice, autoApproved: false });
    expect(option.requiredConditions).toBeInstanceOf(Array);
  });

  it.each(['按金额10%考核', '每件20元，重复发生加倍', '每次100元至200元', '按上级要求考核', '附件内容未提供金额'])('does not approve complex or absent standards: %s', (text) => {
    expect(invoke('parsePricingOptions', [text]).every((option: { autoApproved: boolean }) => !option.autoApproved)).toBe(true);
  });

  it('pins known overrides and refuses changed originals or missing targets', () => {
    const catalog = JSON.parse(readFileSync('backend/data/legacy-rules.json', 'utf8'));
    const overrides = JSON.parse(readFileSync('backend/data/pricing-overrides.json', 'utf8'));
    const rule = catalog.rules.find((item: { id: string }) => item.id === 'official-036');
    const changed = invoke('applyPricingOverrides', [catalog.rules, overrides]).find((item: { id: string }) => item.id === rule.id);
    expect(changed.pricingOptions[0]).toMatchObject({ billingType: 'fixed', unitPrice: 40, autoApproved: true });
    expect(() => invoke('applyPricingOverrides', [catalog.rules.map((item: { id: string }) => item.id === rule.id ? { ...rule, original: `${rule.original}已修改` } : item), overrides])).toThrow();
    expect(() => invoke('applyPricingOverrides', [catalog.rules.map((item: { id: string }) => item.id === rule.id ? { ...rule, version: 'different' } : item), overrides])).toThrow();
    expect(() => invoke('applyPricingOverrides', [[], overrides])).toThrow();
  });

  it('classifies every generated rule including attachments', () => {
    const catalog = JSON.parse(readFileSync('backend/data/legacy-rules.json', 'utf8'));
    const types = new Set(['fixed', 'per_piece', 'per_bag', 'per_event', 'per_vehicle', 'per_hour', 'range', 'conditional', 'manual']);
    for (const rule of catalog.rules) for (const option of rule.pricingOptions) {
      expect(types.has(option.billingType), rule.id).toBe(true);
      expect(typeof option.autoApproved, rule.id).toBe('boolean');
      expect(Array.isArray(option.requiredConditions), rule.id).toBe(true);
    }
  });
});
