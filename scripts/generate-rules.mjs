import fs from 'node:fs';
import PizZip from 'pizzip';

try {
const source = fs.readFileSync('西安邮区中心邮件处理中心生产质量考核办法20260819.docx');
const xml = new PizZip(source).file('word/document.xml').asText();
const decode = (value) => value.replace(/<w:tab\/>/g, ' ').replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&quot;/g, '"');
const paragraphs = [...xml.matchAll(/<w:p[ >][\s\S]*?<\/w:p>/g)].map((match) => decode(match[0]).trim()).filter(Boolean);
const headings = new Map([
  ['二、卸车环节', '卸车环节'], ['三、矩阵环节', '矩阵环节'], ['四、小件机环节', '小件机环节'],
  ['五、异形处理环节', '异形处理环节'], ['六、装车环节', '装车环节'], ['七、问题件及疑难邮件处理环节', '问题件及疑难邮件处理环节'],
  ['八、重点指标', '重点指标'], ['九、安全生产', '安全生产'], ['十、其它说明事项', '其他说明事项'],
]);
const general = new Map([['（一）作业效率', '总则·作业效率'], ['（二）规范化操作', '总则·规范化操作'], ['（三）人员管理', '总则·人员管理'], ['（四）其他', '总则·其他']]);
const excluded = new Set(['西安邮区中心邮件处理中心生产质量考核办法', '（2026年8月19日修订版）', '考核办法总则', '邮件逾限量']);
let stage = '总则'; let index = 0; let attachmentMode = false; const counters = new Map(); const seen = new Set();
const unitPatterns = ['小时','车次','台次','人次','班次','袋（件）','袋件','袋/件','人·次','趟次','每车','每袋','每件','每次','每根','每条','每人','每吨','件','袋','次','根','条','车'];
const extractKeywords = (paragraph) => [...new Set(paragraph.split(/[，。；、：\n]+/).flatMap((part) => part.match(/[\u4e00-\u9fa5]{2,6}/g) || []))].slice(0, 12);
function priceOptions(text) {
  const result = []; const fees = [...text.matchAll(/(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?元/g)];
  fees.forEach((fee, i) => {
    const before = text.slice(Math.max(0, fee.index - 32), fee.index); const after = text.slice(fee.index, fee.index + 18);
    const match = unitPatterns.map((u) => ({ u, position: Math.max(before.lastIndexOf(u), after.indexOf(`/${u}`)) })).sort((a, b) => b.position - a.position)[0]?.position >= 0
      ? unitPatterns.map((u) => ({ u, position: Math.max(before.lastIndexOf(u), after.indexOf(`/${u}`)) })).sort((a, b) => b.position - a.position)[0].u : undefined;
    const unit = match ? match.replace(/^每/, '') : '次';
    result.push({ id: `p${i + 1}`, unit, unitPrice: fee[2] ? null : Number(fee[1]), condition: `原文计费标准：${fee[0]}`, needsSupervisorReview: Boolean(fee[2]) || /上级|当年|达标|按照甲方|就高执行/.test(text) });
  });
  return result.length ? result : [{ id: 'supervisor', unit: '待主管认定', unitPrice: null, condition: '原文未给出可直接计算的固定单价', needsSupervisorReview: true }];
}
const rules = [];
for (const paragraph of paragraphs) {
  if (paragraph === '附件2：') { attachmentMode = true; stage = '附件2·需主管认定'; continue; }
  if (attachmentMode) {
    if (seen.has(paragraph) || /^附件2/.test(paragraph) || paragraph.length < 4) continue;
    seen.add(paragraph); index += 1; const count = (counters.get(stage) || 0) + 1; counters.set(stage, count);
    rules.push({ id: `official-${String(index).padStart(3, '0')}`, stage, clause: `${stage}第${count}条`, name: paragraph.replace(/^[（(]\d+[）)]/, '').split(/[，。；]/)[0].slice(0, 32), original: paragraph, pricingOptions: [{ id: 'supervisor', unit: '待主管认定', unitPrice: null, condition: '附件2条款未自动解析计费标准，需主管按原文认定。', needsSupervisorReview: true }], applicableConditions: '附件2内容需结合原文和现场事实由主管认定。', followUpResponsibility: '以附件2原文为准。', version: '20260819', needsSupervisorReview: true, keywords: extractKeywords(paragraph) });
    continue;
  }
  if (general.has(paragraph)) { stage = general.get(paragraph); continue; }
  if (headings.has(paragraph)) { stage = headings.get(paragraph); continue; }
  if (excluded.has(paragraph) || seen.has(paragraph) || /^（\d+）/.test(paragraph) || /^二、|^三、|^四、|^五、|^六、|^七、|^八、|^九、|^十、/.test(paragraph)) continue;
  seen.add(paragraph);
  const count = (counters.get(stage) || 0) + 1; counters.set(stage, count); index += 1;
  const options = priceOptions(paragraph);
  rules.push({
    id: `official-${String(index).padStart(3, '0')}`, stage, clause: `${stage}第${count}条`,
    name: paragraph.replace(/^[（(]\d+[）)]/, '').split(/[，。；]/)[0].slice(0, 32), original: paragraph,
    pricingOptions: options, applicableConditions: '以原文描述、现场事实和适用条件为准。',
    followUpResponsibility: /承担[^。；]*责任|赔偿|延误/.test(paragraph) ? '按原文承担后续连带责任、延误或赔偿责任。' : '无另行载明的后续责任。',
    version: '20260819', needsSupervisorReview: options.some((item) => item.needsSupervisorReview),
    keywords: extractKeywords(paragraph),
  });
}
fs.writeFileSync('public/production-quality-rules.json', JSON.stringify({ version: '20260819', source: '《西安邮区中心邮件处理中心生产质量考核办法》（2026年8月19日修订版）', rules }, null, 2));
console.log(`Generated ${rules.length} official rule records.`);
} catch (error) {
  console.error('规则生成失败：', error instanceof Error ? error.message : error);
  console.error('请确认源 DOCX 位于项目根目录，且文件未损坏或被占用。');
  process.exit(1);
}
