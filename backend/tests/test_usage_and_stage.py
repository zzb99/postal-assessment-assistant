from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from backend.app import ai_usage, ai_writing
from backend.tests.test_ai_optimization import payload, raw


def test_peak_offpeak_unknown_and_holiday_costs(monkeypatch):
    counts = dict(cache_hit_tokens=70, cache_miss_tokens=30, completion_tokens=20)
    at = datetime(2026, 10, 13, 2, tzinfo=timezone.utc)
    cost, band = ai_usage.estimate(counts, at, 'deepseek-flash')
    assert cost == Decimal('0.0002228') and band == 'peak'
    monkeypatch.setattr(ai_usage, 'settings', replace(ai_usage.settings, ai_price_holidays='2026-10-13'))
    assert ai_usage.estimate(counts, at, 'deepseek-flash') == (Decimal('0.0001114'), 'offpeak')
    assert ai_usage.estimate({**counts, 'cache_miss_tokens': None}, at, 'deepseek-flash')[0] is None
    assert ai_usage.estimate(counts, at, 'unknown-model')[0] is None


def test_explicit_operation_stage_conflict_cannot_be_auto_priced(monkeypatch):
    ai_writing.request_cache.clear()
    monkeypatch.setattr(ai_writing, '_chat', lambda *a, **k: raw(finding='小件机发现破损邮件1件未拦截出局'))
    result = ai_writing.compose(payload('小件机发现破损邮件1件未拦截出局'), scope='stage-conflict')
    assert not result['ready']
