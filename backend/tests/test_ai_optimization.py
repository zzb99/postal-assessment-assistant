import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest


def payload(facts="南5装车破损邮件未拦截出局，1件", unit="华阳公司"):
    return SimpleNamespace(facts=facts, incident_date=date(2026, 10, 13), shift="白班", assessment_unit_name=unit)


def raw(rule="official-079", **changes):
    return {"ruleId": rule, "pricingId": "p1", "quantity": 1, "conditionsSatisfied": True,
            "missingFields": [], "finding": "南5装车环节发现1件破损邮件未拦截出局",
            "rectification": "加强现场检查和问题邮件拦截，避免此类情况再次发生", "confidence": "high", **changes}


def test_all_historical_retrieval_cases_and_appendix_are_searchable():
    from backend.app.rule_search import get_index
    index = get_index()
    cases = json.loads((Path(__file__).parent / "fixtures/retrieval_cases.json").read_text(encoding="utf-8"))
    for case in cases:
        found = index.search(case["facts"])
        assert 3 <= len(found) <= 15, case
        assert set(case["expected"]) & {r["id"] for r in found}, (case, [r["id"] for r in found])
    assert any("附件2" in r["stage"] for r in index.search("循环袋绑定率和循环袋库存管理"))
    assert len(index.rules) == 319
    assert index.search("量子纠缠宇宙射线") == []


def test_short_request_sends_candidates_not_full_catalog_or_all_examples(monkeypatch):
    from backend.app import ai_writing
    ai_writing.request_cache.clear()
    calls = []
    monkeypatch.setattr(ai_writing, "_chat", lambda system, user, **kwargs: calls.append((system, user)) or raw())
    result = ai_writing.compose(payload(), scope="device:one")
    assert result["ready"] and result["penalty_amount"] == 100
    prompt = json.loads(calls[0][1])
    assert len(prompt["rules"]) <= 15
    assert "examples" not in prompt or len(prompt["examples"]) <= 2
    assert len(calls) == 1
    assert "公式" not in result["assessment_content"]


def test_same_device_cache_and_display_fields_do_not_recharge(monkeypatch):
    from backend.app import ai_writing
    ai_writing.request_cache.clear()
    calls = []
    monkeypatch.setattr(ai_writing, "_chat", lambda *args, **kwargs: calls.append(1) or raw())
    first = ai_writing.compose(payload(), scope="device:one")
    changed = payload(); changed.incident_date = date(2026, 10, 14)
    second = ai_writing.compose(changed, scope="device:one")
    assert len(calls) == 1 and second["local_cache_hit"] is True
    assert first["assessment_content"] != second["assessment_content"]
    ai_writing.compose(payload(), scope="device:two")
    assert len(calls) == 2


def test_cache_version_and_model_invalidate(monkeypatch):
    from backend.app import ai_writing
    from dataclasses import replace
    ai_writing.request_cache.clear()
    calls = []
    monkeypatch.setattr(ai_writing, "_chat", lambda *args, **kwargs: calls.append(1) or raw())
    ai_writing.compose(payload(), scope="test")
    monkeypatch.setattr(ai_writing, "PROMPT_VERSION", "changed")
    ai_writing.compose(payload(), scope="test")
    monkeypatch.setattr(ai_writing, "settings", replace(ai_writing.settings, deepseek_model="different-model"))
    ai_writing.compose(payload(), scope="test")
    assert len(calls) == 3


def test_missing_conditions_keep_ai_written_draft_and_recheck_locally(monkeypatch):
    from backend.app import ai_writing
    ai_writing.request_cache.clear()
    calls = []
    monkeypatch.setattr(ai_writing, "_chat", lambda *args, **kwargs: calls.append(1) or raw("official-036", conditionsSatisfied=False,
        missingFields=["是否卸车完毕？"], finding="南5卸车口发现1件遗留邮件", rectification="落实一车一清和作业区域检查，避免再次发生"))
    result = ai_writing.compose(payload("南5卸车口发现遗留邮件1件"), scope="device:one")
    assert not result["ready"] and "落实一车一清" in result["draft_content"]
    assert 1 <= len(result["condition_questions"]) <= 2
    assert result["candidate_rules"]
    final = ai_writing.recheck(result["continuation_token"], {"unloading_completed": True, "single_event": True}, scope="device:one")
    assert final["ready"] and final["penalty_amount"] == 40
    assert len(calls) == 1
    with pytest.raises(Exception):
        ai_writing.recheck(result["continuation_token"], {"unloading_completed": True}, scope="device:other")


def test_inflight_identical_requests_are_merged():
    from backend.app.ai_cache import RequestCache
    cache = RequestCache(ttl=10, capacity=2, error_ttl=2)
    gate = threading.Event(); calls = []
    def produce():
        calls.append(1); gate.wait(2); return {"answer": "one"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(cache.get_or_create, "same", produce)
        time.sleep(.02)
        second = executor.submit(cache.get_or_create, "same", produce)
        gate.set()
        assert first.result()[0] == second.result()[0] == {"answer": "one"}
    assert calls == [1]


def test_cache_ttl_capacity_and_failure_cooldown():
    from backend.app.ai_cache import RequestCache
    cache = RequestCache(ttl=.01, capacity=2, error_ttl=10)
    cache.get_or_create("a", lambda: 1); cache.get_or_create("b", lambda: 2); cache.get_or_create("c", lambda: 3)
    assert cache.size <= 2
    time.sleep(.02)
    assert cache.get_or_create("c", lambda: 4) == (4, False)
    attempts = []
    def fail():
        attempts.append(1); raise ValueError("mock failure")
    for _ in range(2):
        with pytest.raises(ValueError): cache.get_or_create("failure", fail)
    assert attempts == [1]


@pytest.mark.parametrize("body,status", [("{truncated", 200), ("{}", 429)])
def test_ai_bad_json_or_429_does_not_retry(monkeypatch, body, status):
    import httpx
    from backend.app import ai
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: calls.append(kwargs) or httpx.Response(status, text=body, request=httpx.Request("POST", "https://api.deepseek.com/chat/completions")))
    with pytest.raises(ai.AiServiceError): ai._chat("JSON", "facts", purpose="test")
    assert len(calls) == 1 and calls[0]["json"]["max_tokens"] == 900


def test_usage_uses_real_numbers_and_never_logs_facts(monkeypatch):
    import httpx
    from backend.app import ai
    from backend.app import ai_usage
    from backend.app.db import Base, engine
    Base.metadata.create_all(engine)
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: httpx.Response(200, json={"choices": [{"message": {"content": "{\"ok\":true}"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 100, "prompt_cache_hit_tokens": 70, "prompt_cache_miss_tokens": 30, "completion_tokens": 20, "total_tokens": 120}}, request=httpx.Request("POST", "https://api.deepseek.com/chat/completions")))
    assert ai._chat("JSON", "sensitive facts do not store", purpose="test") == {"ok": True}
    summary = ai_usage.summary()
    assert summary["today_calls"] >= 1 and summary["today_total_tokens"] >= 120
    assert "sensitive facts" not in json.dumps(summary)
