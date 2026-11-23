"""Real catalog retrieval plus adversarial model outputs; no paid API calls."""
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.rule_search import RuleIndex, prompt_rules, event_supported
from backend.app.policy_store import parse_word
from backend.app import ai_writing

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module', params=['legacy', 'word'])
def index(request):
    if request.param == 'legacy':
        catalog = json.loads((ROOT / 'backend/data/legacy-rules.json').read_text('utf-8'))
    else:
        path = ROOT / '西安邮区中心邮件处理中心生产质量考核办法20260819.docx'
        catalog = parse_word(path.read_bytes(), version='test-word', effective_date='2026-08-19', filename=path.name)
    return RuleIndex(catalog)


@pytest.mark.parametrize('facts', ['小件机遗留1件', '小件机发现遗留邮件1件', '小件机遗留一件', '小件机有一个邮件没清'])
def test_leftover_variants_keep_general_rule_and_exclude_bag_method(index, facts):
    found = index.search(facts)
    assert any('滞留超2小时' in r['original'] for r in found[:3])
    assert not any('三角看袋法' in r['original'] for r in found[:3])
    assert [r['id'] for r in prompt_rules(found)] == [r['id'] for r in found]
    assert all('stage' in r for r in prompt_rules(found))


@pytest.mark.parametrize(('facts', 'text'), [
    ('生产理件岗位缺员5人', '生产人员缺员'),
    ('作业人员抛摔踩踏邮件1次', '暴力分拣'),
    ('垃圾桶发现邮件1件', '垃圾桶内发现邮件'),
    ('卸车完毕后遗留邮件1件', '发现遗留邮件考核40元'),
    ('未穿工服', '三紧'),
])
def test_behavior_beats_location(index, facts, text):
    assert text in index.search(facts)[0]['original']


def payload(facts):
    return SimpleNamespace(facts=facts, incident_date=date(2026, 10, 14), shift='白班', assessment_unit_name='华阳公司')


def response(**changes):
    return {'ruleId': 'official-050', 'pricingId': 'p1', 'quantity': 1,
            'conditionsSatisfied': True, 'missingFields': [], 'confidence': 'high',
            'finding': '小件机遗留1件', 'rectification': '加强现场邮件检查和清理', **changes}


@pytest.mark.parametrize('finding', [
    '小件机遗留1件，未及时清理', '小件机袋内遗留1件',
    '小件机异常邮件遗留1件', '小件机遗留1件，未执行三角看袋法',
    '小件机发现1件邮件未及时处理', '小件机遗留1件，未按规定清理',
    '小件机遗留2件',
])
def test_invented_facts_restore_original_without_paid_retry(monkeypatch, finding):
    ai_writing.request_cache.clear()
    calls = []
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: calls.append(1) or response(finding=finding))
    result = ai_writing.compose(payload('小件机遗留1件'), scope='invention')
    assert '华阳公司存在小件机遗留1件的情况' in result['draft_content']
    assert finding not in result['draft_content']
    assert not result['ready']
    assert len(calls) == 1


def test_wrong_high_confidence_choice_cannot_become_tariff(monkeypatch):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: response(ruleId='official-056'))
    result = ai_writing.compose(payload('小件机遗留1件'), scope='wrong-rule')
    assert not result['ready'] and result['rule_id'] is None
    assert result['disposition'] == 'choose_rule'
    assert all('三角看袋法' not in r['original'] for r in result['candidate_rules'] if not r['clause'].startswith('附件'))


def test_remediation_does_not_import_hourly_condition(monkeypatch):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: response(rectification='请加强巡查，落实异常邮件一小时一清'))
    result = ai_writing.compose(payload('小件机遗留1件'), scope='remediation')
    assert '一小时一清' not in result['draft_content']
    assert '公司请' not in result['draft_content']


@pytest.mark.parametrize(('facts', 'correction'), [
    ('小件机发现破损邮件1件', '加强三角看袋法检查并清除废旧袋牌'),
    ('人员未穿工服', '制止吸烟并落实火种管控'),
    ('小件机遗留1件', '落实每小时清理异常邮件，避免再次发生'),
])
def test_unrelated_remediation_is_not_cached(monkeypatch, facts, correction):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: response(finding=facts, rectification=correction))
    result = ai_writing.compose(payload(facts), scope='unrelated-remediation')
    assert correction not in result['draft_content']
    again = ai_writing.compose(payload(facts), scope='unrelated-remediation')
    assert again['draft_content'] == result['draft_content'] and again['local_cache_hit']


def test_provider_condition_array_does_not_cause_redundant_confirmation(monkeypatch):
    ai_writing.request_cache.clear()
    facts = '卸车完毕后发现遗留邮件1件，属于同一次事项'
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: response(ruleId='official-036', finding=facts,
        conditionsSatisfied=['unloading_completed', 'single_event']))
    result = ai_writing.compose(payload(facts), scope='array-condition')
    assert result['ready'] and result['penalty_amount'] == 40


def test_provider_condition_array_cannot_supply_missing_local_facts(monkeypatch):
    ai_writing.request_cache.clear()
    facts = '卸车口遗留邮件1件'
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: response(ruleId='official-036', finding=facts,
        conditionsSatisfied=['unloading_completed', 'single_event']))
    result = ai_writing.compose(payload(facts), scope='array-missing-facts')
    assert not result['ready'] and result['condition_questions'][0]['id'] == 'unloading_completed'


def test_untimely_does_not_prove_one_hour():
    from backend.app.pricing import _condition
    assert _condition('not_hourly_cleared', '异常邮件未及时清理') is None
    assert _condition('not_hourly_cleared', '异常邮件未执行一小时一清') is True


def test_wrong_exact_evidence_is_rejected(monkeypatch):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: response(matchedEvidence='未执行一小时一清'))
    result = ai_writing.compose(payload('小件机遗留1件'), scope='wrong-evidence')
    assert result['rule_id'] is None and not result['ready']


def test_location_alone_is_not_behavior_evidence(monkeypatch):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: response(matchedEvidence='小件机'))
    result = ai_writing.compose(payload('小件机遗留1件'), scope='location-evidence')
    assert result['rule_id'] is None and not result['ready']


def test_known_stage_with_no_matching_behavior_is_not_supported(index):
    rule = next(r for r in index.rules if '三角看袋法' in r['original'] and '附件' not in r['stage'])
    assert not event_supported('小件机遗留1件', rule)


@pytest.mark.parametrize(('facts', 'expected'), [('工服口袋携带手机', '手机'), ('小件机未戴安全帽', '安全帽')])
def test_background_noun_does_not_override_actual_behavior(index, facts, expected):
    related = [r for r in index.search(facts) if event_supported(facts, r)]
    assert related and expected in related[0]['original']
