"""Offline real application DOCX/PDF rendering, never touches a database or AI."""
import argparse
import importlib.util
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.app import documents


def main(output):
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    examples = [
        ('unloading', '二班', '张智博', '2026年10月13日白班检查发现：华阳公司，南5卸车口卸车完毕后发现遗留邮件1件。现根据《西安邮区中心邮件处理中心生产质量考核办法》卸车环节第11条规定，按本次事项定额考核华阳公司40元。\n\n望华阳公司落实一车一清，作业结束后检查车厢及卸车区域，避免此类情况再次发生。', '肆拾元整'),
        ('smoking', '二班', '张智博、李明', '2026年10月13日白班检查发现：华阳公司，作业人员在生产现场非吸烟区吸烟。现根据《西安邮区中心邮件处理中心生产质量考核办法》安全生产第7条规定，按本次事项定额考核华阳公司500元。\n\n望华阳公司加强消防安全教育，严格落实现场禁烟规定，杜绝此类情况再次发生。', '伍佰元整'),
        ('long-footer', '生产二班', '张智博、李明、王五', '2026年10月13日夜班检查发现：华阳公司，装车环节发现2件破损邮件未拦截出局。现根据《西安邮区中心邮件处理中心生产质量考核办法》装车环节第14条规定，按每件100元，计2件，考核华阳公司共200元。\n\n望华阳公司严格执行破损邮件拦截及加固要求，加强装车检查，避免此类情况再次发生。', '贰佰元整'),
    ]
    summary = []
    for name, team, inspector, content, amount in examples:
        if name == 'long-footer': team, inspector = '二班', '张三、李四、王五'
        # Clause numbering must come from the catalog, not the historical sample.
        catalog = json.loads(Path('backend/data/legacy-rules.json').read_text(encoding='utf-8'))
        rule_id = {'unloading': 'official-036', 'smoking': 'official-107', 'long-footer': 'official-079'}[name]
        clause = next(r['clause'] for r in catalog['rules'] if r['id'] == rule_id)
        import re
        content = re.sub(r'办法》[^规]+规定', '办法》' + clause + '规定', content)
        sample = SimpleNamespace(assessment_unit_name_snapshot='华阳公司', assessment_content=content, penalty_amount_cn=amount, team=team, inspector_name=inspector)
        binary = documents.build_word(sample, fill_time=datetime(2026, 10, 13, tzinfo=timezone.utc))
        (root / (name + '.docx')).write_bytes(binary)
        pdf = documents.convert_word_to_pdf(binary)
        (root / (name + '.pdf')).write_bytes(pdf)
        summary.append({'case': name, 'characters': len(content), 'pdf_bytes': len(pdf)})
    # Compare against the old rendering, not a reconstruction of its appearance.
    documents.settings = replace(documents.settings, document_template=Path('backend/templates/assessment-notice-template-v20260819.docx'))
    documents._fill_body = documents._fill_sdt
    old = SimpleNamespace(assessment_unit_name_snapshot='华阳公司', assessment_content=examples[0][3], penalty_amount_cn='肆拾元整', team='二班', inspector_name='张智博')
    (root / 'before.docx').write_bytes(documents.build_word(old, fill_time=datetime(2026, 10, 13, tzinfo=timezone.utc)))
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('output'); args = parser.parse_args(); main(args.output)
