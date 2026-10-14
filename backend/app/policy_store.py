"""Versioned Word policies on the existing persistent document volume. No model/API calls."""
from __future__ import annotations
import hashlib
import io
import json
import os
import re
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from .config import settings

_LOCK = threading.RLock()
MAX_WORD_BYTES = 5 * 1024 * 1024
BASELINE_DATE = '2026-08-19'


def root() -> Path:
    return settings.document_root / 'policies'


def _manifest():
    path = root() / 'manifest.json'
    return json.loads(path.read_text('utf-8')) if path.exists() else {'current': None, 'versions': []}


def manifest():
    with _LOCK:
        return _manifest()


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _extract_blocks(doc):
    # document order, including tables; do not discard attachments
    for node in doc.element.body.iterchildren():
        if node.tag == qn('w:p'):
            text = ''.join(n.text or '' for n in node.iter(qn('w:t'))).strip()
            if text: yield text
        elif node.tag == qn('w:tbl'):
            for row in node.findall(qn('w:tr')):
                cells = []
                for cell in row.findall(qn('w:tc')):
                    pieces = [ ''.join(n.text or '' for n in paragraph.iter(qn('w:t'))).strip() for paragraph in cell.iter(qn('w:p')) ]
                    cells.append('；'.join(t for t in pieces if t))
                line = ' | '.join(c for c in cells if c)
                if line: yield line


_HEADINGS = {
    '二、卸车环节': '卸车环节', '三、矩阵环节':'矩阵环节', '四、小件机环节':'小件机环节',
    '五、异形处理环节':'异形处理环节', '六、装车环节':'装车环节',
    '七、问题件及疑难邮件处理环节':'问题件及疑难邮件处理环节', '八、重点指标':'重点指标',
    '九、安全生产':'安全生产','十、其它说明事项':'其他说明事项',
    '（一）作业效率':'总则·作业效率','（二）规范化操作':'总则·规范化操作',
    '（三）人员管理':'总则·人员管理','（四）其他':'总则·其他',
}


def parse_word(content: bytes, *, version: str, effective_date: str, filename: str) -> dict:
    if not 100 <= len(content) <= MAX_WORD_BYTES or content[:2] != b'PK':
        raise ValueError('文件不是有效的docx或超过5MB')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if any(name.startswith('word/vba') or 'externalLink' in name for name in z.namelist()):
                raise ValueError('不允许宏或外部链接文档')
            if sum(info.file_size for info in z.infolist()) > 20 * 1024 * 1024:
                raise ValueError('Word解压后体积异常')
        blocks = list(_extract_blocks(Document(io.BytesIO(content))))
    except (ValueError, zipfile.BadZipFile):
        raise
    except Exception as e:
        raise ValueError('无法读取Word正文及表格') from e
    if len(blocks) < 3:
        raise ValueError('文档内容过少，请核对是否上传考核通则')
    stage, counter, rules = '总则', {}, []
    seen = set()
    for value in blocks:
        raw = re.sub(r'\s+', ' ', value).strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        if raw in _HEADINGS:
            stage = _HEADINGS[raw]; continue
        if re.fullmatch(r'附件\s*\d*[：:]?', raw):
            stage = '附件·待核定'; continue
        if re.fullmatch(r'[一二三四五六七八九十]+、.{1,24}(?:环节|指标|说明事项)', raw):
            stage = raw; continue
        if re.fullmatch(r'（[一二三四五六七八九十]+）.{1,24}', raw):
            stage = raw; continue
        if len(raw) < 9 or raw.startswith(('西安邮区中心邮件处理中心生产质量考核办法','（2026年')) or raw == '考核办法总则':
            continue
        counter[stage] = counter.get(stage, 0) + 1
        options = []
        # Conservative extraction for UI display, NOT auto-approved pricing.
        seen_amounts = set()
        for match in re.finditer(r'(?:每(?:件|次|袋|车次|人次|小时)\s*[^，。；]{0,28}?|)(\d{1,8})\s*元\s*/\s*(件|次|袋|车次|人次|小时)', raw):
            amount, unit = match.group(1), match.group(2)
            seen_amounts.add((amount, unit))
        for amount, unit in sorted(seen_amounts):
            options.append({'id': f'manual-{len(options)+1}', 'unit':unit,'unitPrice':amount,
                            'billingType':'manual','needsSupervisorReview':True, 'autoApproved':False, 'requiredConditions':[]})
        if not options:
            options = [{'id':'manual-1','unit':'待核实','unitPrice':None,'billingType':'manual',
                        'needsSupervisorReview':True,'autoApproved':False,'requiredConditions':[]}]
        rules.append({'id':f'policy-{len(rules)+1:04}', 'stage':stage,
                      'clause':f'{stage}第{counter[stage]}条', 'name':raw[:32], 'original':raw,
                      'applicableConditions':'请依据制度原文及现场事实核实', 'followUpResponsibility':'以原文为准',
                      'pricingOptions':options, 'needsSupervisorReview':True, 'version':version, 'keywords':[],
                      'sourcePosition':len(rules)+1})
    if len(rules) < 10:
        raise ValueError('有效条款不足10条，未替换现行制度')
    if len(rules) > 1500:
        raise ValueError('解析条款数量异常，请检查Word')
    title = blocks[0] if 5 < len(blocks[0]) < 100 and ('考核' in blocks[0] or '办法' in blocks[0]) else Path(filename).stem
    return {'version': version, 'effective_date': effective_date,
            'source': title, 'rules': rules, 'parse_method':'local-docx-v1', 'auto_pricing_approved':False}


def select_entry(for_date: date | None = None) -> dict | None:
    data = manifest()
    versions = data['versions']
    if not versions: return None
    if for_date is None:
        return next((v for v in versions if v['id'] == data['current']), None)
    # A restored version governs today and future; earlier incidents keep their historical schedule.
    current = next((v for v in versions if v['id'] == data['current']), None)
    if current and for_date.isoformat() >= current['effective_date'] and data.get('restored'):
        return current
    eligible = [v for v in versions if v['effective_date'] <= for_date.isoformat() and v.get('active', True)]
    return max(eligible, key=lambda x:(x['effective_date'], x['published_at'])) if eligible else None


def catalog_file(for_date: date | None = None) -> Path | None:
    chosen = select_entry(for_date)
    return root()/chosen['catalog'] if chosen else None


def versions_summary() -> list[dict]:
    data = manifest()
    return [{**{k:v[k] for k in ('id','version','effective_date','published_at','rule_count','uploaded_by','sha256')},
             'current':v['id'] == data['current']} for v in reversed(data['versions'])]


@contextmanager
def _publish_lock():
    with _LOCK:
        root().mkdir(parents=True, exist_ok=True)
        with open(root()/'publish.lock', 'a+b') as fd:
            try:
                import fcntl
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
            except ImportError:
                pass
            try: yield
            finally:
                try:
                    import fcntl
                    fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                except ImportError:
                    pass


def publish(content: bytes, *, filename: str, version: str, effective_date: str, user_id: int, allow_major_change: bool = False) -> dict:
    if not re.fullmatch(r'[\w\u4e00-\u9fff.-]{2,64}', version):
        raise ValueError('版本号格式无效')
    if date.fromisoformat(effective_date).year > date.today().year + 5:
        raise ValueError('生效日期不合理')
    catalog = parse_word(content, version=version, effective_date=effective_date, filename=filename)
    # Exact unchanged text in the same production stage may retain its previously
    # audited rate. New or amended text always remains manual until independently verified.
    from .rule_search import get_index
    previous = get_index()
    if len(catalog['rules']) < len(previous.rules) * 0.5 and not allow_major_change:
        raise ValueError(f'新版仅识别到{len(catalog["rules"])}条，旧版有{len(previous.rules)}条。请确认文件完整；若确属重大修订，请勾选允许重大变更后重新上传')
    verified = {(r['stage'], r['original']): r for r in previous.rules if any(
        p.get('autoApproved') is True and p.get('needsSupervisorReview') is False
        for p in r.get('pricingOptions', []))}
    inherited = 0
    for rule in catalog['rules']:
        old = verified.get((rule['stage'], rule['original']))
        if old is None: continue
        # All options are copied together so the previously audited id/conditions remain intact.
        rule['pricingOptions'] = json.loads(json.dumps(old.get('pricingOptions', []), ensure_ascii=False))
        rule['pricingOverride'] = {'version': version,
                                   'originalSha256': hashlib.sha256(rule['original'].encode('utf-8')).hexdigest()}
        rule['needsSupervisorReview'] = old.get('needsSupervisorReview', True)
        inherited += 1
    catalog['inherited_verified_count'] = inherited
    digest = hashlib.sha256(content).hexdigest()
    with _publish_lock():
        data = _manifest()
        if any(v['version']==version for v in data['versions']):
            raise ValueError('版本号已存在；请填写新的制度版本号')
        id_ = uuid.uuid4().hex
        entry = {'id':id_, 'version':version, 'effective_date':effective_date, 'published_at':datetime.now(timezone.utc).isoformat(),
                 'sha256':digest,'uploaded_by':user_id,'rule_count':len(catalog['rules']),'inherited_verified_count': inherited, 'file':f'{id_}.docx','catalog':f'{id_}.json','active':True}
        _atomic_write(root()/entry['file'], content)
        _atomic_write(root()/entry['catalog'], json.dumps(catalog,ensure_ascii=False).encode('utf-8'))
        data['versions'].append(entry)
        data['current'] = id_
        data.pop('restored', None)
        _atomic_write(root()/'manifest.json', json.dumps(data,ensure_ascii=False).encode('utf-8'))
        return entry



def undo_publish(id_: str) -> None:
    """Compensating rollback if the DB audit cannot be committed."""
    with _publish_lock():
        data = _manifest()
        index = next((i for i, v in enumerate(data['versions']) if v['id'] == id_), None)
        if index is None:
            return
        entry = data['versions'].pop(index)
        if data['current'] == id_:
            data['current'] = data['versions'][-1]['id'] if data['versions'] else None
            data.pop('restored', None)
        _atomic_write(root()/'manifest.json', json.dumps(data, ensure_ascii=False).encode('utf-8'))
        # Originals are retained in case they were referenced in a failed request log;
        # manifest no longer references this candidate.


def restore(id_: str) -> dict:
    with _publish_lock():
        data = _manifest()
        entry = next((v for v in data['versions'] if v['id']==id_), None)
        if not entry: raise ValueError('没有找到该历史版本')
        if not (root()/entry['catalog']).is_file(): raise ValueError('历史制度文件缺失，无法恢复')
        data['current'] = id_
        data['restored'] = True
        _atomic_write(root()/'manifest.json', json.dumps(data,ensure_ascii=False).encode('utf-8'))
        return entry
