"""Bounded, opt-in real-model evaluation. Only synthetic cases; never submits a document."""
import argparse
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select
from backend.app import ai_writing
from backend.app.config import settings
from backend.app.db import Base, engine, SessionLocal
from backend.app.models import AiUsage
from backend.app.rule_search import RuleIndex, get_index
from backend.app.policy_store import parse_word

CASES = [
    ('short', '小件机遗留1件', ['official-050', 'official-012'], None),
    ('short', '小件机有一个邮件没清', ['official-050', 'official-012'], None),
    ('short', '携带打火机', ['official-233'], None),
    ('short', '工服口袋携带手机', ['official-028'], None),
    ('complete', '卸车完毕后发现遗留邮件1件，属于同一次事项', ['official-036'], '40'),
    ('complete', '小件机破损异常邮件未执行一小时一清，发生1次', ['official-050'], '100'),
    ('complete', '生产现场非吸烟区发现人员抽烟，属于同一次事项', ['official-107'], '500'),
    ('complete', '生产现场人员未穿工装，属于同一次事项', ['official-114'], '300'),
    ('complete', '南5装车破损邮件未拦截已出局，1件', ['official-079'], '100'),
    ('complete', '生产现场散落邮件已滞留超过2小时，1件', ['official-012'], '20'),
    ('negative', '人员未吸烟，只是携带打火机', ['official-233', 'official-107'], None),
    ('negative', '小件机破损异常邮件已经执行一小时一清，1件', ['official-050'], None),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', default='output/acceptance/recognition.json')
    parser.add_argument('--group', choices=('short', 'complete', 'negative'))
    parser.add_argument('--limit', type=int, choices=range(1, 13), default=12)
    args = parser.parse_args()
    legacy = RuleIndex(json.loads(Path('backend/data/legacy-rules.json').read_text('utf-8')))
    word = Path('西安邮区中心邮件处理中心生产质量考核办法20260819.docx')
    uploaded = RuleIndex(parse_word(word.read_bytes(), version='evaluation', effective_date='2026-08-19', filename=word.name))
    historical = json.loads(Path('backend/tests/fixtures/retrieval_cases.json').read_text('utf-8'))
    report = {'note': 'Existing 24-case retrieval development set, not held-out business accuracy. Live cases are synthetic; no approval/finalization.', 'retrieval': {}, 'live': []}
    for label, index in [('legacy', legacy), ('uploaded_word', uploaded)]:
        rows = []
        for case in historical:
            expected = {r['original'] for r in legacy.rules if r['id'] in case['expected']}
            result = index.search(case['facts'])
            rank = next((i+1 for i, r in enumerate(result) if r['original'] in expected), None)
            rows.append({'facts': case['facts'], 'expected_rank': rank})
        report['retrieval'][label] = {'count': len(rows), 'top1': sum(r['expected_rank'] == 1 for r in rows),
                                    'top3': sum(r['expected_rank'] is not None and r['expected_rank'] <= 3 for r in rows), 'cases': rows}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    save()
    if args.live:
        if not settings.deepseek_api_key or not settings.database_url.startswith('sqlite:') or 'live-ai-recognition' not in settings.database_url:
            raise SystemExit('Requires privately supplied key and isolated live-ai-recognition SQLite database')
        Base.metadata.create_all(engine)
        index = get_index(date(2026, 10, 14))
        ai_writing.request_cache.clear()
        provider = ai_writing._chat
        raw_outputs = []
        def observe(*a, **kw):
            raw = provider(*a, **kw)
            raw_outputs.append(raw)
            return raw
        ai_writing._chat = observe
        selected_cases = [case for case in CASES if args.group is None or case[0] == args.group][:args.limit]
        for group, facts, expected_ids, amount in selected_cases:
            expected = {r['original'] for r in legacy.rules if r['id'] in expected_ids}
            payload = SimpleNamespace(facts=facts, incident_date=date(2026, 10, 14), shift='白班', assessment_unit_name='华阳公司')
            try:
                result = ai_writing.compose(payload, scope='recognition-synthetic-evaluation')
                repeated = ai_writing.compose(payload, scope='recognition-synthetic-evaluation')
                chosen = next((r for r in index.rules if r['id'] == result['rule_id']), None)
                correct_clause = bool(chosen and chosen['original'] in expected)
                row = {'group': group, 'facts': facts, 'selected': chosen['clause'] if chosen else None,
                       'clause_correct': correct_clause, 'ready': result['ready'], 'amount': str(result['penalty_amount']),
                       'expected_amount': amount, 'questions': result['condition_questions'], 'draft': result['draft_content'],
                       'cache_hit': repeated['local_cache_hit'], 'reason': result['reason'],
                       'model_output': raw_outputs[-1],
                       'passed': (correct_clause and result['ready'] and str(result['penalty_amount']) == amount) if amount else not result['ready']}
            except Exception as error:
                row = {'group': group, 'facts': facts, 'error_type': type(error).__name__, 'passed': False}
                report['live'].append(row)
                save()
                break  # Never retry a paid failure automatically.
            report['live'].append(row)
            save()
            print(json.dumps({k: row[k] for k in ('facts', 'selected', 'ready', 'amount', 'passed')}, ensure_ascii=False), flush=True)
        with SessionLocal() as db:
            report['usage'] = [{key: getattr(row, key) for key in ('model', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'elapsed_ms', 'success')}
                               for row in db.scalars(select(AiUsage).where(AiUsage.event_kind == 'provider'))]
        report['actual_invoice_cny'] = None
        save()
    print(json.dumps({'retrieval': {k: {f: v[f] for f in ('count', 'top1', 'top3')} for k, v in report['retrieval'].items()},
                      'live_count': len(report['live']), 'live_passed': sum(r['passed'] for r in report['live'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
