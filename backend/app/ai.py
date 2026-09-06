from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache

import httpx

from .config import settings
from .documents import format_cn_date


class AiServiceError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def rule_catalog() -> dict:
    path = settings.base_dir / "public" / "production-quality-rules.json"
    if not path.is_file():
        raise AiServiceError("正式制度目录未部署")
    return json.loads(path.read_text(encoding="utf-8"))


def _chat(system_prompt: str, user_prompt: str) -> dict:
    if not settings.deepseek_api_key:
        raise AiServiceError("服务器尚未配置DeepSeek密钥")
    try:
        response = httpx.post(
            settings.deepseek_api_url,
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"},
            json={
                "model": settings.deepseek_model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=45,
        )
        if response.status_code == 402:
            raise AiServiceError("DeepSeek账户余额不足")
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except AiServiceError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AiServiceError("DeepSeek调用失败或返回格式异常") from error


def analyse_assessment(payload) -> dict:
    catalog = rule_catalog()
    rules = catalog.get("rules", [])
    compact = [
        {
            "id": rule["id"], "clause": rule["clause"], "name": rule["name"],
            "original": rule["original"], "pricingOptions": rule["pricingOptions"],
        }
        for rule in rules
    ]
    raw = _chat(
        "你是邮政生产质量考核辅助工具。只能从给定制度目录选择，不得编造条款、单价或数量。"
        "只返回JSON字段ruleId、pricingId、quantity、confidence、reason、needsSupervisorReview。"
        "事实、数量或计价条件不明确时必须把needsSupervisorReview设为true，并将不确定字段设为null。",
        f"事实：{payload.facts}\n正式制度目录：{json.dumps(compact, ensure_ascii=False)}",
    )
    rule = next((item for item in rules if item.get("id") == raw.get("ruleId")), None)
    pricing = next((item for item in (rule or {}).get("pricingOptions", []) if item.get("id") == raw.get("pricingId")), None)
    try:
        quantity = int(raw.get("quantity"))
    except (TypeError, ValueError):
        quantity = None
    safe = bool(rule and pricing and quantity and 1 <= quantity <= 100000 and pricing.get("unitPrice") is not None)
    penalty = Decimal(str(pricing["unitPrice"])) * quantity if safe else None
    if penalty is not None and (penalty < 1 or penalty > 100000000 or penalty != penalty.to_integral_value()):
        safe = False
        penalty = None
    needs_review = bool(raw.get("needsSupervisorReview", True) or not safe or pricing.get("needsSupervisorReview", False) if pricing else True)
    content = None
    if safe:
        content = (
            f"{format_cn_date(payload.incident_date)}{payload.shift}巡查发现：{payload.facts.strip()}。"
            f"根据《西安邮区中心邮件处理中心生产质量考核办法》{rule['clause']}规定，"
            f"按每{pricing['unit']}{pricing['unitPrice']}元执行，数量{quantity}{pricing['unit']}，共计{int(penalty)}元，并承担后续责任。"
            f"望{payload.assessment_unit_name}加强作业人员责任心，避免此类情况再次发生。"
        )
        if len(content) > 600:
            content = None
            needs_review = True
    return {
        "rule_id": rule.get("id") if rule else None,
        "pricing_id": pricing.get("id") if pricing else None,
        "quantity": quantity if safe else None,
        "penalty_amount": penalty if safe else None,
        "assessment_content": content,
        "confidence": raw.get("confidence") if raw.get("confidence") in {"high", "medium", "low"} else "low",
        "reason": str(raw.get("reason") or "未返回判断依据")[:1000],
        "needs_supervisor_review": needs_review,
    }


def answer_policy(question: str) -> dict:
    catalog = rule_catalog()
    rules = catalog.get("rules", [])
    compact = [{"id": r["id"], "clause": r["clause"], "name": r["name"], "original": r["original"]} for r in rules]
    raw = _chat(
        "你是邮政生产质量制度问答助手。只能依据给定条款回答，不得编造。"
        "只返回JSON字段ruleIds、conclusion、recommendedAction、consequence、needsSupervisorReview；ruleIds最多3个。",
        f"问题：{question.strip()}\n正式制度条款：{json.dumps(compact, ensure_ascii=False)}",
    )
    valid_ids = {r["id"] for r in rules}
    rule_ids = [value for value in raw.get("ruleIds", []) if value in valid_ids][:3]
    return {
        "rule_ids": rule_ids,
        "conclusion": str(raw.get("conclusion") or "未找到明确条款")[:2000],
        "recommended_action": str(raw.get("recommendedAction") or "请提交主管人工认定")[:2000],
        "consequence": str(raw.get("consequence") or "制度依据不足，不能直接给出处罚结论")[:2000],
        "needs_supervisor_review": bool(raw.get("needsSupervisorReview", True) or not rule_ids),
    }
