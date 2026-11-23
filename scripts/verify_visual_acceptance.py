"""Real application Word/PDF fixtures; no AI and no production database."""
import argparse
from datetime import datetime
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from pypdf import PdfReader
from backend.app import documents


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='output/acceptance/visual')
    parser.add_argument('--pdftoppm', required=True)
    args = parser.parse_args()
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    prefix = '2026年10月14日白班检查发现：华阳公司卸车完毕后发现遗留邮件1件。现根据《西安邮区中心邮件处理中心生产质量考核办法》卸车环节规定，按本次事项考核华阳公司40元。'
    remediation = '加强作业现场检查，落实一车一清，作业结束后检查车厢及卸车区域，及时清理邮件并明确交接责任，避免同类问题再次发生。'
    rows = []
    for length in (120, 200, 300, 420, 600):
        body = prefix + '\n\n望华阳公司' + (remediation * 12)[:max(1, length - len(prefix) - 8)] + '。'
        sample = SimpleNamespace(assessment_unit_name_snapshot='华阳公司', assessment_content=body,
                                 penalty_amount_cn='肆拾元整', team='二班', inspector_name='张智博')
        name = f'body-{length}'
        word = documents.build_word(sample, fill_time=datetime(2026, 10, 14, 10, 30, tzinfo=ZoneInfo('Asia/Shanghai')))
        (output / f'{name}.docx').write_bytes(word)
        row = {'case': name, 'characters': len(body), 'docx_sha256': hashlib.sha256(word).hexdigest()}
        try:
            pdf = documents.convert_word_to_pdf(word)
            path = output / f'{name}.pdf'; path.write_bytes(pdf)
            reader = PdfReader(BytesIO(pdf))
            text = ''.join(page.extract_text() for page in reader.pages)
            for required in ('邮件处理中心', '通信生产考核通知单', '业务主管', '负责人', '填报日期', '备注', '二班张智博', '肆拾元整'):
                if required not in text.replace(' ', ''):
                    raise AssertionError(f'missing PDF text: {required}')
            assert text.replace(' ', '').count('二班张智博') == 1
            subprocess.run([args.pdftoppm, '-scale-to', '1600', '-png', '-singlefile', str(path), str(output / name)], check=True, capture_output=True)
            # Convert that same DOCX again in an independent LibreOffice profile.
            repeat = output / f'{name}-word-rerender.pdf'
            repeat.write_bytes(documents.convert_word_to_pdf(word))
            subprocess.run([args.pdftoppm, '-scale-to', '1600', '-png', '-singlefile', str(repeat), str(output / f'{name}-word-rerender')], check=True, capture_output=True)
            same = (output / f'{name}.png').read_bytes() == (output / f'{name}-word-rerender.png').read_bytes()
            assert same, 'Same archived DOCX rendered with different visible pixels'
            row.update(status='rendered', pages=len(reader.pages), same_word_pdf_pixels=same, pdf_sha256=hashlib.sha256(pdf).hexdigest())
        except documents.DocumentGenerationError as error:
            row.update(status='safely_rejected', reason=str(error))
        rows.append(row)
    reference = output / 'supplied-template.pdf'
    reference.write_bytes(documents.convert_word_to_pdf(Path('public/assessment-notice-template.docx').read_bytes()))
    subprocess.run([args.pdftoppm, '-scale-to', '1600', '-png', '-singlefile', str(reference), str(output / 'supplied-template')], check=True, capture_output=True)
    (output / 'results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
