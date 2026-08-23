from decimal import Decimal, ROUND_HALF_UP

_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_UNITS = ("", "拾", "佰", "仟")
_BIG_UNITS = ("", "万", "亿", "兆")


def _four_to_cn(value: int) -> str:
    result = ""
    zero = False
    for position in range(3, -1, -1):
        digit = (value // (10 ** position)) % 10
        if digit:
            if zero:
                result += "零"
                zero = False
            result += _DIGITS[digit] + _UNITS[position]
        elif result:
            zero = True
    return result.rstrip("零")


def amount_to_chinese(amount: Decimal) -> str:
    """将最多两位小数的非负金额转换为人民币大写。"""
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < 0:
        raise ValueError("金额不能为负数")
    cents = int(amount * 100)
    integer, fraction = divmod(cents, 100)
    integer_amount = integer
    if integer == 0:
        integer_text = "零"
    else:
        groups: list[int] = []
        while integer:
            groups.append(integer % 10000)
            integer //= 10000
        parts: list[str] = []
        pending_zero = False
        for index in range(len(groups) - 1, -1, -1):
            group = groups[index]
            if group == 0:
                pending_zero = bool(parts)
                continue
            if parts and (pending_zero or group < 1000):
                parts.append("零")
            parts.append(_four_to_cn(group) + _BIG_UNITS[index])
            pending_zero = False
        integer_text = "".join(parts)
    if fraction == 0:
        return f"{integer_text}元整"
    jiao, fen = divmod(fraction, 10)
    fraction_text = ""
    if jiao:
        fraction_text += _DIGITS[jiao] + "角"
    elif integer_amount and fen:
        fraction_text += "零"
    if fen:
        fraction_text += _DIGITS[fen] + "分"
    return f"{integer_text}元{fraction_text}"
