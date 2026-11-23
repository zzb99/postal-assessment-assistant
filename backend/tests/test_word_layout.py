from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from lxml import etree
from backend.app import documents


def example(content='检查发现遗留邮件1件。依据制度按本次事项考核40元。\n\n望华阳公司落实一车一清，避免再次发生。'):
    return SimpleNamespace(assessment_unit_name_snapshot='华阳公司', assessment_content=content, penalty_amount_cn='肆拾元整', team='二班', inspector_name='张智博')


def test_body_is_real_paragraphs_16pt_song_left_aligned():
    data = documents.build_word(example(), fill_time=datetime(2026, 10, 13, tzinfo=timezone.utc))
    root = etree.fromstring(ZipFile(BytesIO(data)).read('word/document.xml'))
    ns = documents.NS
    paragraphs = root.xpath('.//w:tbl/w:tr[2]/w:tc[2]/w:p', namespaces=ns)
    assert len(paragraphs) == 2
    for p in paragraphs:
        assert p.xpath('string(w:pPr/w:jc/@w:val)', namespaces=ns) in {'left', 'both'}
        assert p.xpath('.//w:rPr/w:sz/@w:val', namespaces=ns) == ['32', '32']
        assert p.xpath('.//w:rPr/w:rFonts/@w:eastAsia', namespaces=ns) == ['宋体', '宋体']
    text = ''.join(root.xpath('.//w:t/text()', namespaces=ns))
    assert text.count('2026年10月13日') == 1
    assert text.count('二班张智博') == 1
    assert len(root.xpath('.//w:tbl', namespaces=ns)) == 1


def test_overlong_footer_rejected_not_wrapped_or_silently_shrunk():
    data = example(); data.inspector_name = '张' * 100
    with pytest.raises(documents.DocumentGenerationError): documents.build_word(data)
