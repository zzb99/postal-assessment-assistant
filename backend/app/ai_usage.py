"""Only numeric telemetry is persisted: never prompts, facts, users, keys or responses."""
import logging
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .db import SessionLocal
from .models import AiUsage

log = logging.getLogger(__name__)
CN = ZoneInfo("Asia/Shanghai")


def estimate(usage, at, model):
    local = at.astimezone(CN)
    peak = local.weekday() < 5 and local.date().isoformat() not in settings.ai_price_holidays.split(",") and (9 <= local.hour < 12 or 14 <= local.hour < 18)
    band = "peak" if peak else "offpeak"
    if model != settings.ai_price_model or any(usage.get(k) is None for k in ("cache_hit_tokens", "cache_miss_tokens", "completion_tokens")):
        return None, band
    try:
        values = (settings.ai_peak_hit_cny, settings.ai_peak_miss_cny, settings.ai_peak_output_cny) if peak else (settings.ai_offpeak_hit_cny, settings.ai_offpeak_miss_cny, settings.ai_offpeak_output_cny)
        prices = [Decimal(p) for p in values]
        if any(not p.is_finite() or p < 0 for p in prices):
            return None, band
        cost = sum(Decimal(usage[k]) * price for k, price in zip(("cache_hit_tokens", "cache_miss_tokens", "completion_tokens"), prices)) / Decimal(1000000)
        return cost, band
    except (ValueError, InvalidOperation):
        return None, band


def record(*, purpose, model, started_at=None, elapsed_ms=0, success=True, usage=None, event_kind="provider", error_code=None):
    at = started_at or datetime.now(timezone.utc)
    incoming = usage if isinstance(usage, dict) else {}
    def number(key):
        value = incoming.get(key)
        return value if type(value) is int and value >= 0 else None
    counts = {key: number(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    counts["cache_hit_tokens"] = number("prompt_cache_hit_tokens")
    counts["cache_miss_tokens"] = number("prompt_cache_miss_tokens")
    if event_kind != "provider":
        counts = {key: 0 for key in counts}
    cost, band = estimate(counts, at, model)
    if event_kind != "provider":
        cost = Decimal(0)
    try:
        with SessionLocal.begin() as session:
            session.add(AiUsage(started_at=at, purpose=purpose[:32], model=model[:100], event_kind=event_kind,
                                elapsed_ms=max(0, elapsed_ms), success=success, estimated_cny=cost,
                                price_band=band, error_code=error_code[:32] if error_code else None, **counts))
    except SQLAlchemyError:
        # The operation remains usable, but telemetry loss is explicitly visible in logs.
        log.error("AI usage persistence failed; verify ai_usage migration (no request content logged)")


def summary():
    now = datetime.now(CN)
    start = datetime.combine(now.date() - timedelta(days=6), datetime.min.time(), tzinfo=CN).astimezone(timezone.utc)
    with SessionLocal() as session:
        rows = list(session.scalars(select(AiUsage).where(AiUsage.started_at >= start).order_by(AiUsage.id)))
    def day(row):
        at = row.started_at if row.started_at.tzinfo else row.started_at.replace(tzinfo=timezone.utc)
        return at.astimezone(CN).date()
    paid = [r for r in rows if r.event_kind == "provider"]
    today = [r for r in paid if day(r) == now.date()]
    cached = [r for r in rows if r.event_kind in {"cache", "followup"}]
    times = sorted(r.elapsed_ms for r in paid)
    def money(items):
        return None if any(r.estimated_cny is None for r in items) else str(sum((r.estimated_cny for r in items), Decimal(0)))
    completed = [r for r in rows if r.event_kind == "result" and r.success]
    assessment_calls = [r for r in paid if r.purpose in {"quick_compose", "admin_compose"}]
    total_cost = money(assessment_calls)
    return {
        "today_calls": len(today), "today_total_tokens": sum(r.total_tokens or 0 for r in today),
        "today_estimated_cny": money(today), "seven_day_estimated_cny": money(paid),
        "average_assessment_cny": str(Decimal(total_cost) / len(completed)) if total_cost is not None and completed else None,
        "local_cache_hit_rate": len(cached) / max(1, len(cached) + len(paid)),
        "mean_latency_ms": sum(times) / len(times) if times else 0,
        "p95_latency_ms": times[max(0, math.ceil(len(times) * .95) - 1)] if times else 0,
        "unknown_usage_calls": sum(r.total_tokens is None for r in paid),
        "today_prompt_tokens": sum(r.prompt_tokens or 0 for r in today),
        "today_cache_hit_tokens": sum(r.cache_hit_tokens or 0 for r in today),
        "today_cache_miss_tokens": sum(r.cache_miss_tokens or 0 for r in today),
        "today_output_tokens": sum(r.completion_tokens or 0 for r in today),
        "provider_success_rate": sum(r.success for r in paid) / len(paid) if paid else None,
        "failure_reasons": {code: sum(r.error_code == code for r in paid if not r.success) for code in {r.error_code or 'unknown' for r in paid if not r.success}},
        "price_note": "配置价估算，实际账单以DeepSeek为准；缺少usage显示未知。平均费用按最近7天AI完成稿计，不等于正式归档账单。法定节假日需配置。",
        "days": [{"date": (now.date() - timedelta(days=i)).isoformat(),
                  "calls": len([r for r in paid if day(r) == now.date() - timedelta(days=i)]),
                  "total_tokens": sum(r.total_tokens or 0 for r in paid if day(r) == now.date() - timedelta(days=i)),
                  "estimated_cny": money([r for r in paid if day(r) == now.date() - timedelta(days=i)])} for i in range(6, -1, -1)],
    }
