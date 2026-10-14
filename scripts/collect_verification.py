"""Collect evidence without copying private environments or runtime databases."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def main():
    output = Path('output/acceptance/evidence'); output.mkdir(parents=True, exist_ok=True)
    archive = Path('D:/下载/考核系统-20261014-直接修改修复版.zip')
    protected = ['test_review_20261014_fixes.py', 'test_pricing.py', 'test_ai_optimization.py',
                 'test_upgrade_guards.py', 'test_usage_and_stage.py', 'test_word_layout.py', 'test_queue.py']
    hashes = []
    with ZipFile(archive) as original:
        for name in protected:
            path = 'backend/tests/' + name
            before = original.read('assessment_system_fixed_20261014/' + path)
            after = Path(path).read_bytes()
            assert before == after, f'Protected test modified: {path}'
            hashes.append({'file': path, 'sha256': hashlib.sha256(after).hexdigest(), 'unchanged': True})
    results = ET.parse('.pytest_cache/delivery.xml').getroot()
    cases = list(results.iter('testcase'))
    guarded = [case for case in cases if case.attrib['classname'].split('.')[-1] + '.py' in protected]
    assert len(guarded) == 99 and all(case.find('failure') is None and case.find('error') is None for case in guarded)
    calls = []
    for database in ('.tmp/live-ai-smoke.sqlite', '.tmp/live-ai-smoke-detail.sqlite', '.tmp/live-ai-smoke-fixed.sqlite'):
        with sqlite3.connect(f'file:{Path(database).resolve().as_posix()}?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            calls.extend(dict(row) for row in db.execute("select model, success, prompt_tokens, completion_tokens, total_tokens, cache_hit_tokens, cache_miss_tokens, estimated_cny, elapsed_ms from ai_usage where event_kind='provider'"))
    report = {'input_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'backend_tests': len(cases), 'backend_failures': sum(case.find('failure') is not None or case.find('error') is not None for case in cases),
              'backend_skipped': sum(case.find('skipped') is not None for case in cases),
              'original_99_tests_passed': len(guarded), 'protected_files': hashes,
              'live_provider_calls': len(calls), 'live_input_tokens': sum(row['prompt_tokens'] or 0 for row in calls),
              'live_output_tokens': sum(row['completion_tokens'] or 0 for row in calls),
              'live_total_tokens': sum(row['total_tokens'] or 0 for row in calls),
              'estimated_cny_from_config': str(sum((Decimal(str(row['estimated_cny'])) for row in calls if row['estimated_cny'] is not None), Decimal('0'))),
              'actual_invoice_cny': None, 'calls': calls,
              'docker_final_runtime': 'BLOCKED_BY_DESKTOP_SOCKET', 'postgres_live': 'NOT_VERIFIED'}
    for source in ('.baseline-backend.log', '.baseline-frontend.log', '.baseline-build.log', '.pytest_cache/delivery.xml',
                   '.pytest_cache/delivery.log', '.pytest_cache/frontend-delivery.log', '.pytest_cache/build-delivery.log',
                   '.pytest_cache/stress-policy.xml', '.pytest_cache/stress-policy.log'):
        if Path(source).exists(): shutil.copyfile(source, output / Path(source).name.lstrip('.'))
    (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in {'calls', 'protected_files'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
