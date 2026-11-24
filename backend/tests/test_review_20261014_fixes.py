from decimal import Decimal
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from backend.app.manual_amount import validate_manual_amount
from backend.app.policy_store import parse_word
from backend.app.rule_search import RuleIndex
from backend.app.ai_writing import _selected_entry


def test_money_mismatch_rejected():
    for text, amount in [
        ('现考核联智公司500元。', Decimal('100')),
        ('每件20元，涉及3件，共60元。', Decimal('20')),
        ('考核500元，金额大写伍佰元整。', Decimal('100')),
    ]:
        with pytest.raises(HTTPException) as err:
            validate_manual_amount(text, amount)
        assert err.value.status_code == 422


def test_money_correct_accepts_rate_plus_total():
    validate_manual_amount('按每件20元，计3件，共60元，考核联智公司60元。', Decimal('60'))


def test_selection_retains_unverified_semantics():
    entry={'raw':{'ruleId':'official-001','pricingId':'option-1','confidence':'medium',
                  'conditionsSatisfied':False,'missingFields':['other']}}
    chosen=_selected_entry(entry, {'rule':'official-107','pricing':'option-2'})
    assert chosen['raw']['ruleId'] == 'official-107'
    assert chosen['raw']['missingFields'] == ['other']
    assert chosen['raw']['conditionsSatisfied'] is False
    assert entry['raw']['ruleId'] == 'official-001'


def test_workwear_synonyms():
    from backend.app.rule_search import get_index
    index = get_index()
    for text in ['未穿工作服', '作业现场没穿工作服', '未穿工装']:
        assert 'official-114' in [r['id'] for r in index.search(text)]


def test_word_parser_keeps_non_price_clause_and_table():
    root=Path(__file__).resolve().parents[2]
    file=next(root.glob('*20260819.docx'))
    catalog=parse_word(file.read_bytes(), version='VERIFY', effective_date='2026-08-19',filename=file.name)
    assert len(catalog['rules']) >= 150
    assert any('吸烟' in r['original'] for r in catalog['rules'])
    assert any('附件' in r['stage'] for r in catalog['rules'])
    assert all(not any(p.get('autoApproved') for p in r['pricingOptions']) for r in catalog['rules'])


def test_invalid_doc_rejected():
    with pytest.raises(ValueError):
        parse_word(b'not a word',version='NEW',effective_date='2026-10-14',filename='bad.docx')


def test_published_version_persists_and_restores_without_ai(tmp_path, monkeypatch, policy_today):
    from dataclasses import replace
    from backend.app import policy_store, rule_search
    from backend.app.config import settings
    original = next(Path(__file__).resolve().parents[2].glob('*20260819.docx'))
    monkeypatch.setattr(policy_store, 'settings', replace(settings, document_root=tmp_path))
    policy_today(date(2026, 10, 14))
    first = policy_store.publish(original.read_bytes(), filename='现行通则.docx',version='TEST-ONE',
                                 effective_date='2026-08-19',user_id=1)
    assert first['inherited_verified_count'] == 8
    assert rule_search.get_index().catalog['version']=='TEST-ONE'
    assert (tmp_path/'policies'/'manifest.json').exists()
    assert (tmp_path/'policies'/first['file']).read_bytes()==original.read_bytes()
    second = policy_store.publish(original.read_bytes(),filename='新通则.docx',version='TEST-TWO',
                                  effective_date='2026-10-14',user_id=2)
    assert rule_search.get_index(date(2026,9,1)).catalog['version']=='TEST-ONE'
    assert rule_search.get_index(date(2026,10,15)).catalog['version']=='TEST-TWO'
    policy_store.restore(first['id'])
    assert rule_search.get_index(date(2026,10,15)).catalog['version']=='TEST-ONE'
    assert second['id'] != first['id']


def test_modified_policy_does_not_inherit_unapproved_amounts(tmp_path, monkeypatch):
    from dataclasses import replace
    from io import BytesIO
    from docx import Document
    from backend.app import policy_store
    from backend.app.config import settings
    original = next(Path(__file__).resolve().parents[2].glob('*20260819.docx'))
    data=Document(original)
    for paragraph in data.paragraphs:
        if '非吸烟区吸烟' in paragraph.text:
            paragraph.text = paragraph.text.replace('500元', '600元')
            break
    output=BytesIO(); data.save(output)
    monkeypatch.setattr(policy_store, 'settings', replace(settings, document_root=tmp_path))
    policy_store.publish(output.getvalue(),filename='调整处罚金额.docx',version='AMENDED',
                         effective_date='2026-10-15',user_id=1)
    from backend.app.rule_search import get_index
    rule=next(r for r in get_index().rules if '非吸烟区吸烟' in r['original'])
    assert '600元' in rule['original']
    assert not any(o.get('autoApproved') for o in rule['pricingOptions'])


def test_policy_publish_compensating_rollback(tmp_path, monkeypatch):
    from dataclasses import replace
    from backend.app import policy_store
    from backend.app.config import settings
    doc=next(Path(__file__).resolve().parents[2].glob('*20260819.docx')).read_bytes()
    monkeypatch.setattr(policy_store, 'settings', replace(settings, document_root=tmp_path))
    old=policy_store.manifest()
    entry=policy_store.publish(doc,filename='测试.docx',version='ROLLBACK',effective_date='2026-10-14',user_id=1)
    assert policy_store.manifest()['current']==entry['id']
    policy_store.undo_publish(entry['id'])
    assert policy_store.manifest()==old
