"""Conservative check: never allow stated monetary total to contradict structured amount."""
import re
import unicodedata
from .money import amount_to_chinese
from decimal import Decimal
from fastapi import HTTPException

TOTAL = re.compile(r"(?:共计|共|合计|总计|总额|考核|处罚|罚款|扣款|金额为|计)(?:[\s：:，,\u4e00-\u9fff]{0,16}?)?(?P<value>\d+(?:\.\d{1,2})?)\s*元")
ANY_AMOUNT = re.compile(r"(?<![0-9])([0-9]+(?:\.[0-9]{1,2})?)\s*元")
CN_AMOUNT = re.compile(r'([零〇一二两三四五六七八九十百千万亿壹贰叁肆伍陆柒捌玖拾佰仟]+)\s*[元圆](?:整|正)?')


def _chinese_integer(value):
    digits = dict(zip('零〇一二两三四五六七八九壹贰叁肆伍陆柒捌玖', (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 1, 2, 3, 4, 5, 6, 7, 8, 9)))
    units = {'十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000}
    total = section = digit = 0
    for char in value:
        if char in digits: digit = digits[char]
        elif char in units:
            section += (digit or 1) * units[char]; digit = 0
        elif char == '万':
            total += (section + digit) * 10000; section = digit = 0
        elif char == '亿':
            total = (total + section + digit) * 100000000; section = digit = 0
    return Decimal(total + section + digit)


def validate_manual_amount(content: str, amount: Decimal) -> None:
    """Reject conflicting written totals; distinguish unit prices from totals.

    If wording is not reliably parseable, request clarification rather than guessing.
    """
    content = unicodedata.normalize('NFKC', content)
    if re.search(r'\d+[,.]\d{3}\s*元|[元圆]\s*[零〇一二三四五六七八九壹贰叁肆伍陆柒捌玖\d]+\s*[角分]', content):
        raise HTTPException(422, '金额表达存在分隔符或角分，请明确本次考核合计整数金额')
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
    for match in CN_AMOUNT.finditer(content):
        # A unit price is not a total; require a separately stated total in that case.
        prefix = content[max(0, match.start() - 10):match.start()]
        if re.search(r'每(?:件|次|袋|车|人|小时)(?:考核|处罚|罚款)?\s*$', prefix):
            if not totals:
                raise HTTPException(422, '正文仅有中文单价，请写明本次合计金额')
            continue
        if _chinese_integer(match.group(1)) != amount:
            raise HTTPException(422, '正文中文金额与填写金额不一致，请核对本次合计金额')
    # An empty total is allowed for manually drafted facts; final amount is shown separately
    # on the signed Word, but a contradictory total is never allowed.
