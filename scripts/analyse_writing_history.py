"""Analyse every valid historical notice; never treat old money as current policy."""
import argparse
import hashlib
import json
import re
from collections import Counter
from io import BytesIO
from pathlib import Path
from statistics import median
from zipfile import ZipFile
from lxml import etree as E

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
CATEGORIES = {'卸车': ('卸车', '接卸'), '装车': ('装车', '装发'), '小件机': ('小件机', '供件', '补码', '开拆'),
              '安全生产': ('吸烟', '抽烟', '安全', '工服', '槽口'), '收容': ('收容', '袋牌', '格口'),
              '矩阵': ('矩阵', '理件', '细分'), '错发白送': ('错发', '白送'), '现场管理': ('6S', '定置', '人员', '现场')}


def analyse(source, output):
    records = []; sizes = Counter(); openings = Counter(); lengths = []; corrections = Counter(); paragraph_counts = Counter()
    with ZipFile(source) as archive:
        for item in archive.infolist():
            if not item.filename.lower().endswith('.docx') or Path(item.filename).name.startswith('~$'): continue
            binary = archive.read(item)
            with ZipFile(BytesIO(binary)) as word:
                root = E.fromstring(word.read('word/document.xml'))
                cells = root.xpath('.//w:tbl[1]/w:tr[2]/w:tc[2]', namespaces=NS)
                if not cells: raise ValueError('Notice has no assessment content cell')
                cell = cells[0]
                paragraphs = [''.join(p.xpath('.//w:t/text()', namespaces=NS)).strip() for p in cell.findall('w:p', NS)]
                paragraphs = [p for p in paragraphs if p]
                text = '\n'.join(paragraphs)
                category = '错发白送' if ('错发' in text or '白送' in text) else next((name for name, markers in CATEGORIES.items() if any(marker in text + item.filename for marker in markers)), '现场管理')
                sizes.update(cell.xpath('.//w:rPr/w:sz/@w:val', namespaces=NS))
                paragraph_counts[len(paragraphs)] += 1; lengths.append(len(text))
                openings.update(re.findall(r'巡查发现|检查发现|视频回放发现|现场发现', text))
                for phrase in ('加强作业人员', '加强现场管理', '避免此类情况再次发生', '落实一车一清', '严格执行', '加强业务培训'):
                    if phrase in text: corrections[phrase] += 1
                records.append({'source_sha256': hashlib.sha256(binary).hexdigest(), 'category': category, 'body_characters': len(text),
                                'paragraph_count': len(paragraphs), 'references_20260825': '20260825' in text})
    if len(records) != 86: raise ValueError(f'Expected all 86 valid notices, got {len(records)}')
    result = {'source_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest(), 'valid_notices': len(records), 'excluded_lock_files': 4,
              'usage': '仅归纳文风，历史处罚金额不是现行制度；事实与责任单位不得复制', 'categories': dict(Counter(r['category'] for r in records)),
              'font_half_points': dict(sizes), 'body_characters': {'minimum': min(lengths), 'median': median(lengths), 'maximum': max(lengths)},
              'paragraph_counts': dict(paragraph_counts), 'openings': dict(openings), 'rectification_phrases': dict(corrections), 'records': records}
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('source'); parser.add_argument('output'); args = parser.parse_args()
    analyse(args.source, args.output)
