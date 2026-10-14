"""Conservative check: never allow stated monetary total to contradict structured amount."""
import re
from .money import amount_to_chinese
from decimal import Decimal
from fastapi import HTTPException

TOTAL = re.compile(r"(?:共计|共|合计|总计|总额|考核|处罚|罚款|扣款|金额为|计)(?:[\s：:，,\u4e00-\u9fff]{0,16}?)?(?P<value>\d+(?:\.\d{1,2})?)\s*元")
ANY_AMOUNT = re.compile(r"(?<![0-9])([0-9]+(?:\.[0-9]{1,2})?)\s*元")


def validate_manual_amount(content: str, amount: Decimal) -> None:
    """Reject conflicting written totals; distinguish unit prices from totals.

    If wording is not reliably parseable, request clarification rather than guessing.
    """
    totals = {Decimal(match.group('value')) for match in TOTAL.finditer(content)}
    if len(totals) > 1 or (totals and amount not in totals):
        raise HTTPException(422, '考核正文金额与填写金额不一致，请修改一致后再生成')
    if not totals:
        numbers = {Decimal(value) for value in ANY_AMOUNT.findall(content)}
        if numbers and amount not in numbers and not re.search(r"每(?:件|次|袋|车|人|小时)\s*\d+(?:\.\d+)?\s*元|\d+(?:\.\d+)?\s*元\s*/\s*(?:件|次|袋|车|人|小时)", content):
            raise HTTPException(422, '正文中存在与填写金额不同的数字，请写明本次考核总金额')
    chinese_totals = set(re.findall(r'[零壹贰叁肆伍陆柒捌玖拾佰仟万亿]+元整', content))
    if chinese_totals and (len(chinese_totals) > 1 or amount_to_chinese(amount) not in chinese_totals):
        raise HTTPException(422, '正文大写金额与表单金额不一致，请核对')
    # An empty total is allowed for manually drafted facts; final amount is shown separately
    # on the signed Word, but a contradictory total is never allowed.
