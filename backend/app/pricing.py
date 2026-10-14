"""Deterministic, conservative pricing. No model output is pricing evidence."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any


MAX_QUANTITY = 100000
MAX_AMOUNT = Decimal("100000000")
NUMBER = r"\d+(?:\.\d+)?|[零一二两三四五六七八九十百千万]+"
COUNT = re.compile(rf"(?<![\d.负-])({NUMBER})\s*(袋[（(]件[）)]|袋件|人次|车次|小时|件|袋|次|人|辆|车)")
CONDITION_QUESTIONS = {
    "unloading_completed": "是否已卸车完毕后才发现遗留邮件？",
    "single_event": "本次填报是否只涉及同一次违规事项（不是多次合并）？",
    "duration_gt_2h": "散落邮件是否已滞留严格超过2小时？",
    "confirmed_violation": "是否已实际核实并确认人为隐匿、毁弃或窃取邮件？",
    "abnormal_mail": "是否属于破损、水湿、补码或飘落等异常邮件？",
    "not_hourly_cleared": "是否确实未执行异常邮件一小时一清？",
    "left_facility": "不合格邮件是否已经出局或互盘？",
    "not_intercepted_or_reinforced": "装车时是否未按规定拦截或加固不合格邮件？",
    "not_long_line_unloading": "是否未执行一字长龙卸车法？",
    "confirmed_smoking": "是否实际发现人员吸烟（仅携带烟草或打火机不算吸烟）？",
    "nonsmoking_area": "是否发生在场院或生产现场的非吸烟区？",
    "dress_noncompliance": "生产现场是否实际存在未穿工服、三紧不合规或长发未戴发套？",
}


def _number(value: str) -> Decimal:
    """Parse bounded Chinese integer sections and decimal Arabic numbers exactly."""
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return Decimal(value)
    digits = {char: index for index, char in enumerate("零一二三四五六七八九")}
    digits["两"] = 2
    total = section = digit = 0
    for char in value:
        if char in digits:
            digit = digits[char]
        elif char == "万":
            total += (section + digit or 1) * 10000
            section = digit = 0
        else:
            section += (digit or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            digit = 0
    return Decimal(total + section + digit)


def _evidence(text: str, yes: str, no: str) -> bool | None:
    if re.search(no, text):
        return False
    return True if re.search(yes, text) else None


def _single_event(text: str) -> bool | None:
    if re.search(r"(?:不|不是|并非|未)(?:属于|是)?\s*同一(?:次|事项)|不同(?:车辆|车次|事项)|多(?:次|辆|车)", text):
        return False
    for number, unit in COUNT.findall(text):
        if unit in {"次", "辆", "车", "车次"} and _number(number) > 1:
            return False
    if re.search(r"同一(?:次事项|次|事项)|(?:共|发生|涉及|计)\s*(?:1|一)\s*次", text):
        return True
    return None


def _duration(text: str) -> bool | None:
    if re.search(r"(?:未|没|不|尚未|还没|没有)(?:曾|达到|达|超过|超|滞留|遗留)|(?:不足|不到|少于|不满).{0,8}小时", text):
        return False
    found = re.findall(rf"(?:滞留|遗留).{{0,6}}?(超过|超|大于|已达|达到|已)?\s*({NUMBER})\s*小时", text)
    if not found:
        return None
    # Contradictory durations are not automatic evidence.
    values = [(_number(number), prefix) for prefix, number in found]
    return all(hours > 2 or (hours == 2 and prefix in {"超过", "超", "大于"}) for hours, prefix in values)


def _condition(name: str, text: str) -> bool | None:
    if name == "single_event":
        return _single_event(text)
    if name == "duration_gt_2h":
        return _duration(text)
    if name == "confirmed_smoking":
        # Location names and prohibition signs do not prove that someone smoked.
        text = re.sub(r"非吸烟区|禁止吸烟区|吸烟区|吸烟标志|吸烟规定", "", text)
    patterns = {
        "unloading_completed": (
            r"(?:卸车|接卸)(?:作业)?(?:已|已经)?(?:完毕|完成|结束)|卸完车",
            r"(?:未|没有|尚未|还没).{0,5}(?:卸车|接卸|卸完)|(?:卸车|接卸).{0,5}(?:未|没有|尚未|还没).{0,3}(?:完毕|完成|结束)"),
        "confirmed_violation": (
            r"(?:经核实|已确认|已核实|查实|证实).{0,12}(?:人为隐匿|毁弃|窃取)",
            r"疑似|涉嫌|尚未核实|未确认|未发现|(?:并非|不是|没有).{0,5}(?:隐匿|毁弃|窃取)"),
        "abnormal_mail": (r"异常|破损|水湿|补码|飘落", r"无异常|没有异常|并非异常|无破损|没有破损"),
        "not_hourly_cleared": (
            r"(?:未|没有|未能|不曾)(?:严格|按要求)?(?:执行|落实|做到)?(?:一小时一清|每小时清理)|未及时清理",
            r"(?:已|已经|按时|正常)(?:执行|落实|做到)?(?:一小时一清|每小时清理)|并非未执行一小时一清"),
        "left_facility": (
            r"(?:已|已经|造成|导致)(?:不合格邮件|邮件)?(?:出局|互盘)|已发出|未(?:及时|按规定)?拦截(?:邮件)?(?:出局|互盘)",
            r"(?:未|没有|尚未|还没|并未|并非)(?:实际|真正|全部|完成|被)?(?:出局|互盘|发出)|(?:出局|互盘)(?:前|之前)"),
        "not_intercepted_or_reinforced": (
            r"未(?:及时|按规定)?(?:拦截|加固)|没有(?:拦截|加固)|漏拦截",
            r"已(?:及时|按规定)?(?:拦截并加固|加固并拦截)|并非未拦截"),
        "not_long_line_unloading": (
            r"未(?:按要求)?(?:执行|采用)一字长龙卸车法|没有(?:执行|采用)一字长龙卸车法",
            r"(?:已|已经|正常)(?:执行|采用)一字长龙卸车法|并非未执行一字长龙卸车法"),
        "confirmed_smoking": (
            r"(?<!禁止)(?<!严禁)(?<!不准)吸烟|抽烟|抽香烟",
            r"(?:未|没有|没|并非|不是|不曾)(?:实际|正在|在)?(?:吸烟|抽烟|抽香烟)|未发现.{0,8}(?:吸烟|抽烟)|(?:禁止|严禁|不准).{0,6}(?:吸烟|抽烟)"),
        "nonsmoking_area": (
            r"非吸烟区|禁烟区|禁止吸烟(?:区域|场所)",
            r"(?:不是|并非|不在|未在|没有在|非)(?:在)?非吸烟区|(?<!非)(?<!禁止)吸烟区|(?:不是|并非)禁烟区"),
        "dress_noncompliance": (
            r"(?:未|没有|没)(?:按规定)?(?:穿|着)(?:工作服|工服)|(?:三紧).{0,5}(?:不合规|不符合|未落实)|未(?:执行|落实)三紧|(?:长发|女职工).{0,8}未戴发套|(?:穿着|身穿)(?:长裙|长衣|帽衫)|(?:衣领|袖口|下摆).{0,4}(?:未收紧|未扎紧|不紧)",
            r"(?:已|已经|按要求)(?:按要求)?(?:穿|着)(?:工作服|工服)|三紧(?:已)?(?:符合要求|符合规定|合规)|(?:并非|不是|不存在)未穿(?:工作服|工服)"),
    }
    if name not in patterns:
        return None
    if name == 'dress_noncompliance':
        text = text.replace('工装', '工服')
    return _evidence(text, *patterns[name])


def _question(name: str) -> dict[str, str]:
    if name == "billing_quantity":
        return {"id": name, "question": "请明确本条款对应的计费数量（不是涉及邮件件数推算的次数）。", "kind": "integer"}
    return {"id": name, "question": CONDITION_QUESTIONS.get(name, f"请确认适用条件：{name}"), "kind": "boolean"}


def _quantity_evidenced(text: str, quantity: int, unit: str, billing_type: str) -> bool:
    aliases = {"袋件": {"件", "袋", "袋件", "袋（件）", "袋(件)"}, "车次": {"车次", "辆", "车"}}
    allowed = aliases.get(unit, {unit})
    if billing_type == "fixed":
        allowed = {"件", "袋", "袋件", "次", "车次", "车", "辆"}
    counts = [(_number(number), found) for number, found in COUNT.findall(text)]
    matching = {number for number, found in counts if found in allowed}
    # A total and a violating subset cannot both be taken as the billing quantity.
    return quantity in matching and (billing_type == "fixed" or len(matching) == 1)


def _approved(rule: dict, option: dict) -> bool:
    pin = rule.get("pricingOverride", {})
    actual = hashlib.sha256(rule.get("original", "").encode("utf-8")).hexdigest()
    return (option.get("autoApproved") is True and option.get("needsSupervisorReview") is False
            and pin.get("version") == rule.get("version") and pin.get("originalSha256") == actual)


def calculate(rule: dict, pricing_id: str, facts: str, raw_quantity: Any, confirmations: dict | None = None) -> dict:
    """Return a price only for pinned standards, explicit quantities and satisfied conditions.

    Confirmations are local answers supplied by the human, not model booleans.
    They can resolve missing evidence but never contradict an explicit negative fact.
    Fixed rates return one billed matter, independent of the number of involved pieces.
    """
    option = next((item for item in rule.get("pricingOptions", []) if item.get("id") == pricing_id), {})
    billing_type, unit = option.get("billingType", "manual"), option.get("unit", "待核定")
    result = {"ready": False, "quantity": None, "amount": None, "unit": unit,
              "billing_type": billing_type, "questions": [], "reason": "", "disposition": "manual"}
    if not _approved(rule, option) or billing_type not in {"fixed", "per_piece", "per_bag", "per_event", "per_vehicle", "per_hour"}:
        result["reason"] = f"该条款尚未核准自动计价，请按原文手动核定。原文：{rule.get('original', '')}"
        return result
    confirmations = confirmations if isinstance(confirmations, dict) else {}
    text = unicodedata.normalize("NFKC", facts)
    questions = []
    for condition in option.get("requiredConditions", []):
        evidence = _condition(condition, text)
        answer = confirmations.get(condition)
        if evidence is False or answer is False:
            result.update(disposition='not_applicable', reason='已确认不满足本条款的适用条件，不按此条处罚；可核对其他条款或保留草稿。')
            return result
        if evidence is not True and answer is not True:
            questions.append(_question(condition))
    given = confirmations.get("billing_quantity", raw_quantity)
    quantity_valid = type(given) is int and 1 <= given <= MAX_QUANTITY
    fixed_without_piece_count = billing_type == "fixed" and given is None and "billing_quantity" not in confirmations
    if fixed_without_piece_count:
        # Its sole billed matter is proven by required single_event, not a guessed piece count.
        given = 1
    elif not quantity_valid or ("billing_quantity" not in confirmations and not _quantity_evidenced(text, given, unit, billing_type)):
        questions.append(_question("billing_quantity"))
    if questions:
        result['disposition'] = 'needs_conditions'
        result["questions"] = questions[:2]
        result["reason"] = "适用条件或计费数量尚未核实，不生成处罚金额。"
        return result
    billed_quantity = 1 if billing_type == "fixed" else given
    try:
        amount = Decimal(str(option.get("unitPrice"))) * billed_quantity
        if not amount.is_finite() or amount < 1 or amount > MAX_AMOUNT or amount != amount.to_integral_value():
            raise ValueError("non-integral or out of bounds")
    except (InvalidOperation, ValueError):
        result["reason"] = "制度计价数据无效，不生成处罚金额。"
        return result
    result.update(ready=True, disposition='ready', quantity=billed_quantity, amount=amount,
                  reason="按已核准原文定额计价，不乘邮件件数。" if billing_type == "fixed" else "按已核准原文及明确计费数量计算。")
    return result
