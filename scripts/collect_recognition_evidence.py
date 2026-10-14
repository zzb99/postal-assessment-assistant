"""Collect numeric usage and immutable regression evidence, without private data."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def main():
    protected = ['test_review_20261014_fixes.py', 'test_pricing.py', 'test_ai_optimization.py',
                 'test_upgrade_guards.py', 'test_usage_and_stage.py', 'test_word_layout.py', 'test_queue.py']
    target = Path('output/acceptance/recognition-evidence')
    target.mkdir(parents=True, exist_ok=True)
    with ZipFile('D:/下载/考核系统-20261014-直接修改修复版.zip') as archive:
        hashes = []
        for name in protected:
            path = Path('backend/tests') / name
            content = path.read_bytes()
            assert content == archive.read('assessment_system_fixed_20261014/' + path.as_posix())
            hashes.append({'file': path.as_posix(), 'sha256': hashlib.sha256(content).hexdigest()})
    cases = list(ET.parse('.pytest_cache/recognition-release.xml').getroot().iter('testcase'))
    passed = lambda c: all(c.find(tag) is None for tag in ('failure', 'error', 'skipped'))
    original = [c for c in cases if c.attrib['classname'].split('.')[-1] + '.py' in protected]
    assert len(original) == 99 and all(passed(c) for c in original)
    rows = []
    for name in ('v3', 'diagnostic', 'v4'):
        path = Path(f'.tmp/live-ai-recognition-{name}.sqlite').resolve()
        with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            rows.extend(dict(row) for row in db.execute("SELECT started_at, model, prompt_tokens, completion_tokens, total_tokens, estimated_cny FROM ai_usage WHERE event_kind='provider'"))
    first = min(row['started_at'] for row in rows)
    preview = Path('.tmp/acceptance/database.sqlite').resolve()
    with sqlite3.connect(f'file:{preview.as_posix()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        preview_calls = [dict(row) for row in db.execute("SELECT started_at, model, prompt_tokens, completion_tokens, total_tokens, estimated_cny FROM ai_usage WHERE event_kind='provider' AND started_at >= ?", (first,))]
    final = json.loads(Path('output/acceptance/recognition-final.json').read_text('utf-8'))
    summary = {'backend': {'total': len(cases), 'passed': sum(passed(c) for c in cases)},
               'original_99_unchanged_and_passed': True, 'protected_test_hashes': hashes,
               'synthetic_final_live_cases': len(final['live']), 'synthetic_final_live_passed': sum(r['passed'] for r in final['live']),
               'paid_evaluation_calls': len(rows), 'preview_calls_since_evaluation_started': len(preview_calls),
               'total_tokens_evaluation': sum(r['total_tokens'] or 0 for r in rows),
               'total_tokens_preview': sum(r['total_tokens'] or 0 for r in preview_calls),
               'configured_estimated_cny': sum(float(r['estimated_cny'] or 0) for r in rows + preview_calls),
               'actual_invoice_cny': None, 'notes': 'Synthetic target cases only, not a held-out business accuracy estimate. Docker/PostgreSQL production acceptance remains unverified.'}
    for name in ('recognition-release.xml', 'recognition-release.log', 'recognition-frontend.log', 'recognition-build.log'):
        source = Path('.pytest_cache') / name
        if source.exists():
            shutil.copyfile(source, target / name)
    (target / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'protected_test_hashes'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
