"""Local, narrow tariff grammar. Ambiguity never becomes a monetary decision."""
import hashlib
import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher

AMOUNT = re.compile(r'\d+(?:\.\d+)?\s*元')
COMPLEX = re.compile(r'以上|以下|以内|超过|不足|至|[~～%％]|\d\s*[-—－]\s*\d|加倍|翻倍|累计|另行|另加|同时|分别|视情|酌情|情节|重复|再次|首次|如果|若|否则|依据|按照.*标准|按.*比例|损失|附件|参照|并处|扣分|小时|分钟|每日|每天')
RATE = re.compile(r'(?:每(?P<unit>件|次)\s*(?:考核|处罚|罚款|扣款)?\s*(?P<amount>\d{1,8})\s*元|(?:考核|处罚|罚款|扣款)?\s*(?P<slash_amount>\d{1,8})\s*元\s*/\s*(?P<slash_unit>件|次))')
FIXED = re.compile(r'(?:定额(?:考核|处罚)?|一次性(?:考核|处罚)?|一经发现(?:考核|处罚)?|考核|处罚|罚款)\s*(?P<amount>\d{1,8})\s*元')


def simple_tariff(original: str) -> dict | None:
    text = unicodedata.normalize('NFKC', original)
    if len(AMOUNT.findall(text)) != 1 or COMPLEX.search(text) or '|' in text or len(text) > 120:
        return None
    match = RATE.search(text)
    fixed = False
    if match:
        unit = match.group('unit') or match.group('slash_unit')
        amount = match.group('amount') or match.group('slash_amount')
    else:
        match = FIXED.search(text)
        if not match or '每' in text or '/' in text:
            return None
        fixed, unit, amount = True, '事项', match.group('amount')
    if not 1 <= Decimal(amount) <= Decimal('100000000'):
        return None
    # A tariff-only fragment or an additional subclause is not a complete standard.
    premise = re.sub(r'^\s*(?:\d+[.、)]|[（(]\d+[）)])\s*', '', text[:match.start()]).strip(' ，,。；;')
    if not 3 <= len(premise) <= 70 or re.search(r'[。；;]|(?:且|并|以及|或|如|当).{2,}', premise):
        return None
    if text[match.end():].strip(' 。；;，,'):
        return None
    return {'id': 'simple-1', 'unit': unit, 'unitPrice': int(amount),
            'billingType': 'fixed' if fixed else ('per_piece' if unit == '件' else 'per_event'),
            'autoApproved': False, 'needsSupervisorReview': True,
            'requiredConditions': ['clause_applies'] + (['single_event'] if fixed else []),
            'condition': original, 'parser': 'simple-tariff-v1'}


def identity(text: str) -> str:
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'^\s*(?:\d+[.、)]|[（(]\d+[）)])\s*', '', text)
    return re.sub(r'\s+', '', AMOUNT.sub('<金额>', text))


def differences(catalog: dict, previous) -> dict:
    by_text = {}
    for old in previous.rules:
        by_text.setdefault((old['stage'], old['original']), []).append(old)
    remaining = {old['id']: old for old in previous.rules}
    rows = []
    for rule in catalog['rules']:
        exact = next((r for r in by_text.get((rule['stage'], rule['original']), []) if r['id'] in remaining), None)
        old = exact
        if old is None:
            possible = [r for r in remaining.values() if r['stage'] == rule['stage']]
            old = max(possible, key=lambda r: SequenceMatcher(None, identity(r['original']), identity(rule['original'])).ratio(), default=None)
            if old and SequenceMatcher(None, identity(old['original']), identity(rule['original'])).ratio() < .8:
                old = None
        if old:
            remaining.pop(old['id'], None)
        rows.append({'kind': 'unchanged' if exact else 'modified' if old else 'added',
                     'old_id': old['id'] if old else None, 'new_id': rule['id'],
                     'old_sha256': hashlib.sha256(old['original'].encode()).hexdigest() if old else None,
                     'new_sha256': hashlib.sha256(rule['original'].encode()).hexdigest(),
                     'amount_changed': bool(old and AMOUNT.findall(old['original']) != AMOUNT.findall(rule['original'])),
                     'before': old['original'] if old else None, 'after': rule['original']})
    rows.extend({'kind': 'removed', 'old_id': old['id'], 'new_id': None,
                 'old_sha256': hashlib.sha256(old['original'].encode()).hexdigest(),
                 'new_sha256': None, 'amount_changed': False, 'before': old['original'], 'after': None}
                for old in remaining.values())
    return {'summary': {kind: sum(row['kind'] == kind for row in rows) for kind in ('unchanged', 'modified', 'added', 'removed')}, 'changes': rows}


def approve_simple(catalog: dict, previous) -> int:
    count = 0
    for rule in catalog['rules']:
        if rule.get('pricingOverride') or '附件' in rule['stage'] or rule.get('sourceLocation', {}).get('kind') != 'paragraph':
            continue
        option = simple_tariff(rule['original'])
        if option is None:
            continue
        # Amendments to existing wording/rates stay manual, even when the grammar is simple.
        similar = [r for r in previous.rules if r['stage'] == rule['stage'] and
                   SequenceMatcher(None, identity(r['original']), identity(rule['original'])).ratio() >= .8]
        if any(r['original'] != rule['original'] for r in similar):
            rule['pricingWarning'] = '与旧版相近条款有修改，金额及条件需按原文人工核定'
            continue
        option.update(autoApproved=True, needsSupervisorReview=False)
        rule.update(pricingOptions=[option], needsSupervisorReview=False,
                    pricingOverride={'version': catalog['version'], 'originalSha256': hashlib.sha256(rule['original'].encode()).hexdigest()})
        count += 1
    return count
