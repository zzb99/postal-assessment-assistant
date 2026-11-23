from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app import ai_writing
from backend.tests.test_ai_optimization import payload, raw


@pytest.mark.parametrize('phrase', ['处以伍佰元罚款', '扣款五百元', '罚金500圆'])
def test_ai_cannot_invent_chinese_or_alternate_penalties(phrase):
    with pytest.raises(ai_writing.AiServiceError):
        ai_writing._wording(payload(), raw(finding='发现破损邮件，' + phrase))


def test_unknown_semantic_condition_cannot_be_silently_discarded(monkeypatch):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: raw(conditionsSatisfied=False, missingFields=['other']))
    assert not ai_writing.compose(payload(), scope='guard')['ready']


def test_sequential_continuation_keeps_unit_context(monkeypatch):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: raw('official-036', conditionsSatisfied=False,
        missingFields=['unloading_completed', 'single_event'], finding='南5卸车口发现1件遗留邮件'))
    data = payload('南5卸车口发现遗留邮件1件'); data.assessment_unit_id = 7
    first = ai_writing.compose(data, scope='device:guard')
    second = ai_writing.recheck(first['continuation_token'], {'unloading_completed': True}, scope='device:guard')
    third = ai_writing.recheck(second['continuation_token'], {'single_event': True}, scope='device:guard')
    assert third['ready'] and third['_context']['unit_id'] == 7


def test_proposal_invalidates_on_catalog_change(monkeypatch):
    from backend.app.rule_search import get_index
    form = SimpleNamespace(incident_date=date(2026, 10, 13), shift='白班', assessment_unit_id=1)
    result = dict(quantity=1, penalty_amount=Decimal('100'), assessment_content='正文', operation_stage='装车环节', regulation_version='20260819', rule_id='official-079', pricing_id='p1')
    form.ai_proposal = ai_writing.sign_proposal(result, form, 'guard')
    form.quantity = 1; form.penalty_amount = Decimal('100'); form.assessment_content = '正文'
    monkeypatch.setattr(get_index(), 'digest', 'new-digest')
    with pytest.raises(HTTPException): ai_writing.verify_proposal(form, 'guard')


@pytest.mark.parametrize('facts,expected', [('现场抽烟', 'official-107'), ('现场未穿工装', 'official-114'), ('装车时重件压轻件', 'official-214')])
def test_colloquial_retrieval(facts, expected):
    from backend.app.rule_search import get_index
    assert expected in {r['id'] for r in get_index().search(facts)}


@pytest.mark.parametrize('facts,finding', [('发现2件破损邮件未拦截出局', '发现三件破损邮件未拦截出局'), ('发现2件破损邮件，3名人员', '发现3件破损邮件')])
def test_numeric_unit_evidence_cannot_be_reassigned(facts, finding):
    with pytest.raises(ai_writing.AiServiceError): ai_writing._wording(payload(facts), raw(finding=finding))


def test_chinese_quantity_may_be_rendered_in_arabic_without_changing_evidence():
    finding, _ = ai_writing._wording(payload('装车发现破损邮件一件未拦截出局'), raw(finding='装车发现1件破损邮件未拦截出局'))
    assert '1件' in finding


def test_reconfirmation_edits_locally_without_ai_and_locks_price(monkeypatch):
    from backend.app.schemas import QuickAssessmentInput
    from uuid import uuid4
    form = QuickAssessmentInput(request_id=uuid4(), incident_date=date(2026, 10, 13), shift='白班', assessment_unit_id=1,
        assessment_unit_name='华阳公司', team='二班', inspector_name='张三', quantity=1, penalty_amount=40,
        assessment_content='2026年10月13日白班检查发现：华阳公司，卸车完毕后发现遗留邮件1件。根据第36条规定，考核40元。\n\n望华阳公司加强检查。')
    result = dict(quantity=1, penalty_amount=40, assessment_content=form.assessment_content, operation_stage='卸车环节', regulation_version='20260819', rule_id='official-036', pricing_id='p1')
    form.ai_proposal = ai_writing.sign_proposal(result, form, 'guard')
    changed = form.assessment_content.replace('加强检查', '落实一车一清和作业区域检查')
    token = ai_writing.reconfirm(form, changed, 'guard')
    form.ai_proposal = token; form.assessment_content = changed
    assert ai_writing.verify_proposal(form, 'guard')['content'] == changed
    with pytest.raises(HTTPException): ai_writing.reconfirm(form, changed.replace('40元', '400元'), 'guard')
    with pytest.raises(HTTPException): ai_writing.reconfirm(form, changed.replace('卸车完毕后', '尚未卸车完毕时'), 'guard')
