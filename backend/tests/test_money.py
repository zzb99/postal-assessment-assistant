from decimal import Decimal

from backend.app.money import amount_to_chinese


def test_amount_to_chinese_preserves_jiao_and_fen() -> None:
    assert amount_to_chinese(Decimal("0")) == "零元整"
    assert amount_to_chinese(Decimal("0.01")) == "零元壹分"
    assert amount_to_chinese(Decimal("0.50")) == "零元伍角"
    assert amount_to_chinese(Decimal("500")) == "伍佰元整"
    assert amount_to_chinese(Decimal("10000.05")) == "壹万元零伍分"
