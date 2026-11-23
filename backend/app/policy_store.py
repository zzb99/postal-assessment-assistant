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
from functools import wraps
from contextlib import contextmanager
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from .config import settings

_LOCK = threading.RLock()
_LOCAL = threading.local()
MAX_WORD_BYTES = 5 * 1024 * 1024
BASELINE_DATE = '2026-08-19'


def root() -> Path:
    return settings.document_root / 'policies'


def _manifest():
    path = root() / 'manifest.json'
    return json.loads(path.read_text('utf-8')) if path.exists() else {'current': None, 'versions': []}


def manifest():
    with _publish_lock():
        if not getattr(_LOCAL, 'transaction', False):
            recover_pending()
        return _manifest()


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        with temp.open('wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
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
        document = Document(io.BytesIO(content))
        blocks = list(_extract_blocks(document))
        locations = []
        for index, node in enumerate(document.element.body.iterchildren()):
            if node.tag == qn('w:p'):
                if ''.join(node.itertext()).strip():
                    locations.append({'kind': 'paragraph', 'block': index + 1,
                                      'numbering': bool(node.find('.//' + qn('w:numPr')) is not None)})
            elif node.tag == qn('w:tbl'):
                for row_index, row in enumerate(node.findall(qn('w:tr'))):
                    if any(t.text for t in row.iter(qn('w:t'))):
                        locations.append({'kind': 'table', 'block': index + 1, 'row': row_index + 1})
    except (ValueError, zipfile.BadZipFile):
        raise
    except Exception as e:
        raise ValueError('无法读取Word正文及表格') from e
    if len(blocks) < 3:
        raise ValueError('文档内容过少，请核对是否上传考核通则')
    stage, counter, rules = '总则', {}, []
    for block_index, value in enumerate(blocks):
        raw = re.sub(r'\s+', ' ', value).strip()
        if not raw:
            continue
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
        from .policy_pricing import simple_tariff
        simple = simple_tariff(raw)
        if simple:
            options = [simple]  # Preview candidates remain unapproved until publish comparison.
        rules.append({'id':f'policy-{len(rules)+1:04}', 'stage':stage,
                      'clause':f'{stage}第{counter[stage]}条', 'name':raw[:32], 'original':raw,
                      'applicableConditions':'请依据制度原文及现场事实核实', 'followUpResponsibility':'以原文为准',
                      'pricingOptions':options, 'needsSupervisorReview':True, 'version':version, 'keywords':[],
                      'sourcePosition':block_index + 1,
                      'sourceLocation':locations[block_index] if block_index < len(locations) else {'kind': 'unknown'}})
    if len(rules) < 10:
        raise ValueError('有效条款不足10条，未替换现行制度')
    if len(rules) > 1500:
        raise ValueError('解析条款数量异常，请检查Word')
    title = blocks[0] if 5 < len(blocks[0]) < 100 and ('考核' in blocks[0] or '办法' in blocks[0]) else Path(filename).stem
    return {'version': version, 'effective_date': effective_date,
            'source': title, 'rules': rules, 'parse_method':'local-docx-v2', 'auto_pricing_approved':False,
            'source_blocks': [{'position': i + 1, 'text': text, 'location': locations[i] if i < len(locations) else {}}
                              for i, text in enumerate(blocks)],
            'parse_warnings': ['自动编号保留在原始Word，定位以正文块及表格行号为准；表格/附件和复杂计费需核对原文。']}


def select_entry(for_date: date | None = None) -> dict | None:
    data = manifest()
    versions = data['versions']
    if not versions: return None
    if for_date is None:
        return next((v for v in versions if v['id'] == data['current']), None)
    # A restored version governs today and future; earlier incidents keep their historical schedule.
    current = next((v for v in versions if v['id'] == data['current']), None)
    for event in reversed(data.get('restorations', [])):
        if event['from_date'] <= for_date.isoformat():
            later = [v for v in versions if v['published_at'] > event['at'] and v['effective_date'] <= for_date.isoformat()]
            if not later:
                return next(v for v in versions if v['id'] == event['id'])
            break
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
        if getattr(_LOCAL, 'depth', 0):
            _LOCAL.depth += 1
            try:
                yield
            finally:
                _LOCAL.depth -= 1
            return
        root().mkdir(parents=True, exist_ok=True)
        with open(root()/'publish.lock', 'a+b') as fd:
            try:
                import fcntl
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
            except ImportError:
                import msvcrt
                fd.seek(0)
                if not fd.read(1):
                    fd.write(b'0'); fd.flush()
                fd.seek(0)
                msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
            _LOCAL.depth = 1
            try: yield
            finally:
                _LOCAL.depth = 0
                try:
                    import fcntl
                    fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                except ImportError:
                    import msvcrt
                    fd.seek(0)
                    msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)


def recover_pending(session=None):
    """Reconcile a crashed filesystem/DB commit using a durable operation audit marker."""
    pending = root() / 'pending.json'
    if not pending.exists():
        return
    from sqlalchemy import select
    from .db import SessionLocal
    from .models import AuditLog
    state = json.loads(pending.read_text('utf-8'))
    def committed(db):
        return db.scalar(select(AuditLog.id).where(AuditLog.target_type == 'policy_operation', AuditLog.target_id == state['operation'])) is not None
    if session is None:
        with SessionLocal() as db:
            done = committed(db)
    else:
        done = committed(session)
    _atomic_write(root() / 'manifest.json', json.dumps(state['after'] if done else state['before'], ensure_ascii=False).encode())
    pending.unlink()


@contextmanager
def policy_transaction(session):
    with _publish_lock():
        recover_pending(session)
        before = _manifest()
        operation = uuid.uuid4().hex
        _LOCAL.transaction = True
        _LOCAL.journal = {'operation': operation, 'before': before, 'after': before}
        try:
            yield operation
        except Exception:
            session.rollback()
            recover_pending(session)
            raise
        finally:
            _LOCAL.transaction = False
            _LOCAL.journal = None


def _write_manifest(data):
    journal = getattr(_LOCAL, 'journal', None)
    if journal is not None:
        journal['after'] = data
        _atomic_write(root() / 'pending.json', json.dumps(journal, ensure_ascii=False).encode())
    _atomic_write(root() / 'manifest.json', json.dumps(data, ensure_ascii=False).encode())


def finish_transaction():
    # If deletion fails after DB commit, recovery observes its committed audit marker.
    (root() / 'pending.json').unlink(missing_ok=True)


def _locked(function):
    @wraps(function)
    def run(*args, **kwargs):
        with _publish_lock():
            return function(*args, **kwargs)
    return run


@_locked
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
    from .policy_pricing import approve_simple, differences
    catalog['simple_verified_count'] = approve_simple(catalog, previous)
    catalog['diff'] = differences(catalog, previous)
    digest = hashlib.sha256(content).hexdigest()
    with _publish_lock():
        data = _manifest()
        previous_manifest = {k: v for k, v in data.items() if k != 'versions'}
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
        entry['simple_verified_count'] = catalog['simple_verified_count']
        entry['previous_manifest'] = previous_manifest
        _write_manifest(data)
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
            previous = entry.get('previous_manifest')
            if previous is not None:
                for key in list(data):
                    if key != 'versions': data.pop(key)
                data.update(previous)
            else:
                data['current'] = data['versions'][-1]['id'] if data['versions'] else None
        _atomic_write(root()/'manifest.json', json.dumps(data, ensure_ascii=False).encode('utf-8'))
        # Originals are retained in case they were referenced in a failed request log;
        # manifest no longer references this candidate.


def restore(id_: str) -> dict:
    with _publish_lock():
        data = _manifest()
        entry = next((v for v in data['versions'] if v['id']==id_), None)
        if not entry: raise ValueError('没有找到该历史版本')
        if not (root()/entry['catalog']).is_file() or not (root()/entry['file']).is_file(): raise ValueError('历史制度文件缺失，无法恢复')
        if hashlib.sha256((root()/entry['file']).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('历史制度原件校验失败，无法恢复')
        data['current'] = id_
        data['restored'] = True
        data.setdefault('restorations', []).append({'id': id_, 'from_date': datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(), 'at': datetime.now(timezone.utc).isoformat()})
        _write_manifest(data)
        return entry
