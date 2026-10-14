"""Offline regressions for deterministic pricing, without AI or database calls."""
import importlib
import json
from decimal import Decimal
from pathlib import Path

import pytest


CATALOG = Path(__file__).resolve().parents[2] / "backend/data/legacy-rules.json"


def quote(rule_id, facts, quantity, confirmations=None):
    rules = json.loads(CATALOG.read_text(encoding="utf-8"))["rules"]
    rule = next(item for item in rules if item["id"] == rule_id)
    return importlib.import_module("backend.app.pricing").calculate(rule, "p1", facts, quantity, confirmations)


@pytest.mark.parametrize("rule_id,facts,quantity,expected,billed", [
    ("official-036", "卸车完毕后发现遗留邮件2件，属于同一次事项", 2, "40", 1),
    ("official-013", "经核实已确认人为窃取邮件2件，属于同一次事项", 2, "50000", 1),
    ("official-012", "生产现场散落邮件滞留超过2小时，共3件", 3, "60", 3),
    ("official-040", "未执行一字长龙卸车法，共发生2次", 2, "200", 2),
    ("official-050", "异常破损邮件未执行一小时一清，共发生2次", 2, "200", 2),
    ("official-079", "装车时破损邮件未拦截，已出局，共3件", 3, "300", 3),
])
def test_confirmed_rates(rule_id, facts, quantity, expected, billed):
    result = quote(rule_id, facts, quantity)
    assert result["ready"], result
    assert result["amount"] == Decimal(expected)
    assert result["quantity"] == billed
    assert result["questions"] == []


@pytest.mark.parametrize("facts", [
    "生产现场散落邮件滞留2小时，共2件", "生产现场散落邮件滞留未超过2小时，共2件",
    "生产现场散落邮件滞留不超过3小时，共2件", "生产现场散落邮件滞留不到2小时，共2件",
    "生产现场散落邮件滞留1.5小时，共2件", "生产现场散落邮件滞留尚未超过2小时，共2件",
])
def test_duration_requires_strict_positive_evidence(facts):
    result = quote("official-012", facts, 2)
    assert not result["ready"] and result["amount"] is None
    assert result["questions"] == []
    assert result["disposition"] == "not_applicable"


@pytest.mark.parametrize("facts", [
    "卸车尚未完毕，遗留2件，属于同一次事项", "卸车完毕后遗留2件，不属于同一次事项",
    "卸车完毕后遗留2件，并非同一次事项", "卸车完毕后遗留2件，本次检查共10次",
    "卸车完毕后遗留2件，本次检查涉及100次", "卸车完毕后遗留2件，来自不同车辆",
])
def test_flat_rate_requires_completed_single_event(facts):
    assert not quote("official-036", facts, 2)["ready"]


@pytest.mark.parametrize("quantity", [None, True, False, 1.5, 0, -1, "2", 100001])
def test_raw_quantity_never_coerced_or_defaulted(quantity):
    assert not quote("official-040", "未执行一字长龙卸车法，共2次", quantity)["ready"]


def test_piece_count_does_not_prove_event_count():
    result = quote("official-050", "异常破损邮件10件未执行一小时一清", 10)
    assert not result["ready"]
    assert result["questions"][0]["id"] == "billing_quantity"
    filled = quote("official-050", "异常破损邮件10件未执行一小时一清", 10, {"billing_quantity": 1})
    assert filled["ready"] and filled["amount"] == Decimal("100")


@pytest.mark.parametrize("facts", ["疑似人为窃取2件，属于同一次事项", "已确认并非人为窃取2件，属于同一次事项"])
def test_serious_violation_requires_confirmed_fact(facts):
    assert not quote("official-013", facts, 2)["ready"]


def test_explicit_false_conditions_cannot_be_overridden():
    assert not quote("official-079", "破损邮件尚未出局，共2件", 2, {"left_facility": True})["ready"]
    assert not quote("official-036", "卸车完毕后2件，不属于同一次事项", 2, {"single_event": True})["ready"]


def test_boolean_confirmations_fill_only_missing_conditions():
    result = quote("official-036", "发现遗留邮件2件", 2, {"unloading_completed": True, "single_event": True})
    assert result["ready"] and result["amount"] == Decimal("40")


def test_missing_conditions_are_structured_and_limited():
    result = quote("official-050", "发现邮件10件", 10)
    assert not result["ready"] and len(result["questions"]) <= 2
    assert all(set(question) == {"id", "question", "kind"} for question in result["questions"])


def test_unapproved_rule_cannot_automatically_price():
    result = quote("official-033", "车辆未接卸，发生1次", 1)
    assert not result["ready"] and result["amount"] is None
    assert "原文" in result["reason"]


def test_unknown_pricing_id_and_invalid_confirmations_fail_closed():
    pricing = importlib.import_module("backend.app.pricing")
    result = pricing.calculate({"original": "原文", "pricingOptions": []}, "unknown", "事实", 1)
    assert not result["ready"]
    for value in (True, 1.5, "1", 0, -1):
        assert not quote("official-040", "未执行一字长龙卸车法", 1, {"billing_quantity": value})["ready"]


def test_same_vehicle_alone_does_not_prove_single_event():
    result = quote("official-036", "卸车完毕后发现同一车辆遗留邮件2件", 2)
    assert not result["ready"]
    assert result["questions"][0]["id"] == "single_event"


def test_multiple_piece_counts_require_local_billing_quantity():
    facts = "装车时共10件，其中2件破损邮件未拦截，已出局"
    result = quote("official-079", facts, 10)
    assert not result["ready"]
    assert result["questions"][0]["id"] == "billing_quantity"
    confirmed = quote("official-079", facts, 10, {"billing_quantity": 2})
    assert confirmed["ready"] and confirmed["amount"] == Decimal("200")


@pytest.mark.parametrize("rule_id,facts,confirmations,amount", [
    ("official-036", "卸车完毕后发现遗留邮件", {"single_event": True}, "40"),
    ("official-013", "已核实人为窃取邮件，属于同一次事项", None, "50000"),
    ("official-107", "生产现场非吸烟区发现人员吸烟", {"single_event": True}, "500"),
    ("official-114", "生产现场人员未穿工服上岗", {"single_event": True}, "300"),
    ("official-114", "生产现场未执行三紧，属于同一次事项", None, "300"),
])
def test_fixed_event_confirmation_does_not_require_irrelevant_piece_count(rule_id, facts, confirmations, amount):
    result = quote(rule_id, facts, None, confirmations)
    assert result["ready"], result
    assert result["quantity"] == 1 and result["amount"] == Decimal(amount)


@pytest.mark.parametrize("facts", [
    "生产现场非吸烟区发现人员携带烟草，属于同一次事项",
    "生产现场非吸烟区发现打火机，属于同一次事项",
    "生产现场非吸烟区人员未吸烟，属于同一次事项",
    "生产现场非吸烟区人员没有抽烟，属于同一次事项",
    "生产现场吸烟区发现人员吸烟，属于同一次事项",
    "生产现场发现人员吸烟，属于同一次事项",
])
def test_smoking_requires_actual_smoking_and_nonsmoking_area(facts):
    result = quote("official-107", facts, None)
    assert not result["ready"] and result["amount"] is None
    if any(text in facts for text in ('人员未吸烟', '人员没有抽烟', '生产现场吸烟区')):
        assert result['questions'] == [] and result['disposition'] == 'not_applicable'
    else:
        assert result['questions']


def test_explicit_negative_smoking_fact_cannot_be_confirmed_away():
    result = quote("official-107", "生产现场非吸烟区人员未吸烟", None,
                   {"confirmed_smoking": True, "nonsmoking_area": True, "single_event": True})
    assert not result["ready"]


@pytest.mark.parametrize("facts", ["生产现场已按要求穿工服上岗，属于同一次事项", "生产现场三紧符合要求，属于同一次事项"])
def test_compliant_work_clothes_not_penalized(facts):
    assert not quote("official-114", facts, None, {"dress_noncompliance": True})["ready"]


@pytest.mark.parametrize("quantity", [True, False, 1.5, -1, "1"])
def test_fixed_does_not_coerce_malformed_model_quantity(quantity):
    assert not quote("official-036", "卸车完毕后遗留邮件，属于同一次事项", quantity)["ready"]


def test_unintercepted_departed_mail_expression():
    result = quote("official-079", "装车时破损邮件未拦截出局，共2件", 2)
    assert result["ready"] and result["amount"] == Decimal("200")
    assert not quote("official-079", "装车时破损邮件未拦截，但未出局，共2件", 2)["ready"]


@pytest.mark.parametrize("facts", [
    "生产现场人员未在非吸烟区吸烟，属于同一次事项",
    "生产现场人员没有在非吸烟区抽烟，属于同一次事项",
    "生产现场非吸烟区已禁止人员吸烟，属于同一次事项",
])
def test_smoking_negated_location_or_prohibition_is_not_an_observed_act(facts):
    assert not quote("official-107", facts, None)["ready"]


@pytest.mark.parametrize("facts", ["生产现场不存在未穿工服，属于同一次事项", "生产现场人员不是未穿工服，属于同一次事项"])
def test_denied_clothing_violation_not_penalized(facts):
    assert not quote("official-114", facts, None)["ready"]
