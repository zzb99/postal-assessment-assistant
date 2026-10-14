from decimal import Decimal
import pytest
from fastapi import HTTPException
from backend.app.manual_amount import validate_manual_amount


@pytest.mark.parametrize('text', ['考核一百元。', '合计人民币壹佰圆整。', '罚款１００元。', '考核伍拾元，合计50元。'])
def test_chinese_and_fullwidth_amounts(text):
    validate_manual_amount(text, Decimal('50' if '伍拾' in text else '100'))


@pytest.mark.parametrize('text', ['合计五百元。', '人民币伍佰圆整。', '合计１００元，附件另计500元。', '考核100元五角。'])
def test_conflicting_or_ambiguous_amounts(text):
    with pytest.raises(HTTPException):
        validate_manual_amount(text, Decimal('100'))
