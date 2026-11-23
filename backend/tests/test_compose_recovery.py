"""The screenshot must have a useful next step, without inventing a penalty."""
from dataclasses import replace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import ai_writing, governance
from backend.app.pricing import calculate
from backend.app.rule_search import get_index
from backend.tests.test_ai_optimization import payload, raw
from backend.tests.test_assessment_workflow import reset_database


def rule(rule_id):
    return next(r for r in get_index().rules if r['id'] == rule_id)


def test_lighter_retrieves_related_item_policy_not_phone_or_smoking():
    found = get_index().search('携带打火机。')
    assert found and found[0]['id'] == 'official-233'
    assert not {'official-028', 'official-107'} & {r['id'] for r in found}


def test_negative_answer_excludes_clause_without_repeating_question():
    result = calculate(rule('official-107'), 'p1', '现场抽烟', None, {'nonsmoking_area': False})
    assert not result['ready'] and result['questions'] == []
    assert result['disposition'] == 'not_applicable'


def test_workwear_synonym_does_not_need_reconfirmation():
    result = calculate(rule('official-114'), 'p1', '现场人员未按规定穿工装，同一次事项', None)
    assert result['ready'] and result['amount'] == 300


def test_lighter_added_location_is_replaced_by_original_facts(monkeypatch):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: raw(None, confidence='low',
        finding='现场发现人员携带打火机进入生产现场', rectification='加强火种管理'))
    result = ai_writing.compose(payload('携带打火机。'), scope='recovery')
    assert not result['ready'] and '进入生产现场' not in result['draft_content']
    assert result['writing_notice'] and '打火机' in result['reason']


def test_medium_confidence_can_select_and_continue_locally(monkeypatch):
    ai_writing.request_cache.clear(); calls = []
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: calls.append(1) or raw('official-036',
        confidence='medium', conditionsSatisfied=False, missingFields=['other'],
        finding='卸车口发现1件遗留邮件', rectification='落实一车一清'))
    result = ai_writing.compose(payload('卸车口发现遗留邮件1件'), scope='recovery')
    assert result['candidate_rules'][0]['id'] == get_index().search('卸车口发现遗留邮件1件')[0]['id']
    selected = ai_writing.select_candidate(result['continuation_token'], 'official-036', 'p1', scope='recovery')
    assert selected['condition_questions'][0]['id'] == 'unloading_completed'
    second = ai_writing.recheck(selected['continuation_token'], {'unloading_completed': True}, scope='recovery')
    final = ai_writing.recheck(second['continuation_token'], {'single_event': True}, scope='recovery')
    # Choosing a clause cannot erase an unmodelled semantic prerequisite.
    assert not final['ready'] and final['penalty_amount'] is None and calls == [1]
    assert final['disposition'] == 'needs_conditions'
    assert final['condition_questions'][0]['id'] == 'semantic_confirmed'
    assert '卸车完毕后，卸车口发现' in final['draft_content']
    confirmed = ai_writing.recheck(final['continuation_token'], {'semantic_confirmed': True}, scope='recovery')
    assert confirmed['ready'] and confirmed['penalty_amount'] == 40 and calls == [1]
    rejected = ai_writing.recheck(final['continuation_token'], {'semantic_confirmed': False}, scope='recovery')
    assert not rejected['ready'] and rejected['disposition'] == 'not_applicable'
    with pytest.raises(HTTPException):
        ai_writing.select_candidate(result['continuation_token'], 'official-107', 'p1', scope='another-device')
    with pytest.raises(HTTPException):
        ai_writing.select_candidate(result['continuation_token'], 'official-107', 'p1', scope='recovery')


def test_ai_cannot_remove_an_explicit_negative_finding(monkeypatch):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: raw('official-107',
        finding='发现人员吸烟', rectification='加强消防安全教育'))
    result = ai_writing.compose(payload('人员未吸烟，只是携带打火机'), scope='negative-finding')
    assert '人员未吸烟' in result['draft_content'] and result['writing_notice']


