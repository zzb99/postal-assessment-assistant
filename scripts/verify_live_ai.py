"""Opt-in bounded provider smoke: maximum three calls, no retries, no secrets in output."""
from datetime import date
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import select
from backend.app import ai_writing
from backend.app.config import settings
from backend.app.db import Base, engine, SessionLocal
from backend.app.models import AiUsage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--output', default='output/acceptance/live-ai.json')
    parser.add_argument('--confirm-fixture-facts', action='store_true', help='Locally confirm only the explicit facts in these synthetic acceptance cases')
    parser.add_argument('--generate', action='store_true', help='Generate one isolated real Word/PDF after successful fixture confirmation')
    args = parser.parse_args()
    if not settings.deepseek_api_key:
        raise SystemExit('DEEPSEEK_API_KEY must be supplied privately by the operator')
    if not settings.database_url.startswith('sqlite:') or 'live-ai-smoke' not in settings.database_url:
        raise SystemExit('Use a separate live-ai-smoke SQLite database only')
    Base.metadata.create_all(engine)
    results = []
    ai_writing.request_cache.clear()
    facts_list = ['生产现场非吸烟区发现人员抽烟，属于同一次事项',
                  '卸车完毕后发现遗留邮件1件，属于同一次事项',
                  '小件机破损异常邮件未执行一小时一清，发生1次']
    for index, facts in enumerate(facts_list[:args.limit]):
        payload = SimpleNamespace(facts=facts, incident_date=date(2026, 10, 14), shift='白班', assessment_unit_name='华阳公司', assessment_unit_id=1)
        try:
            result = ai_writing.compose(payload, scope='bounded-live-acceptance', purpose='quick_compose')
            repeated = ai_writing.compose(payload, scope='bounded-live-acceptance', purpose='quick_compose')
            row = {'case': index + 1, 'ready': result['ready'], 'rule_id': result['rule_id'],
                   'confidence': result['confidence'], 'reason': result['reason'], 'clarifications': result['clarifications'],
                   'disposition': result['disposition'], 'local_cache_hit_on_repeat': repeated['local_cache_hit']}
            if not result['ready'] and result.get('continuation_token'):
                selected = next((rule for rule in result['candidate_rules'] if rule['id'] == result['rule_id']), None)
                if selected and selected['pricing_options']:
                    continued = ai_writing.select_candidate(result['continuation_token'], selected['id'], selected['pricing_options'][0]['id'], scope='bounded-live-acceptance')
                    row['after_local_selection'] = {'ready': continued['ready'], 'reason': continued['reason'], 'questions': continued['condition_questions']}
                    if args.confirm_fixture_facts:
                        for _ in range(4):
                            if continued['ready'] or not continued.get('condition_questions'): break
                            questions = continued['condition_questions']
                            if any(q['id'] not in {'semantic_confirmed', 'confirmed_smoking', 'nonsmoking_area', 'single_event', 'unloading_completed', 'abnormal_mail', 'not_hourly_cleared'} for q in questions): break
                            continued = ai_writing.recheck(continued['continuation_token'], {q['id']: True for q in questions}, scope='bounded-live-acceptance')
                        row['after_fixture_fact_confirmation'] = {'ready': continued['ready'], 'amount': str(continued['penalty_amount']), 'local_only': True}
                        if args.generate and continued['ready'] and index == 0:
                            from fastapi.testclient import TestClient
                            from backend.app.main import app
                            from backend.app.quick import device_hash
                            from uuid import uuid4
                            import hashlib
                            headers = {'X-Device-Token': 'c' * 64}
                            signed = ai_writing.sign_proposal(continued, payload, device_hash('c' * 64))
                            with TestClient(app) as client:
                                submission = client.post('/api/quick/assessments', headers=headers, json={
                                    'request_id': str(uuid4()), 'incident_date': str(payload.incident_date), 'shift': payload.shift,
                                    'team': '二班', 'inspector_name': 'AI验收', 'assessment_unit_id': 1, 'assessment_unit_name': '华阳公司',
                                    'quantity': continued['quantity'], 'penalty_amount': str(continued['penalty_amount']),
                                    'assessment_content': continued['assessment_content'], 'ai_proposal': signed})
                                assert submission.status_code == 200, submission.text
                                assessment = submission.json()
                                row['document'] = {'status': assessment['status'], 'number': assessment['assessment_no']}
                                for kind, extension in [('word', 'docx'), ('pdf', 'pdf')]:
                                    file = client.get(f"/api/quick/assessments/{assessment['id']}/documents/{kind}", headers=headers)
                                    assert file.status_code == 200
                                    Path(f'output/acceptance/live-ai-generated.{extension}').write_bytes(file.content)
                                    row['document'][kind + '_sha256'] = hashlib.sha256(file.content).hexdigest()
            results.append(row)
        except Exception as error:
            results.append({'case': index + 1, 'error': type(error).__name__})
            break  # No paid retry loop on provider/configuration problems.
    with SessionLocal() as db:
        calls = [{key: getattr(row, key) for key in ('model', 'success', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'elapsed_ms', 'error_code')}
                 for row in db.scalars(select(AiUsage).where(AiUsage.event_kind == 'provider'))]
    report = {'cases': results, 'provider_calls': calls, 'usage_known': all(row['total_tokens'] is not None for row in calls),
              'actual_invoice_cny': None, 'note': '真实usage；实际费用未取账单，不把配置估算当作账单。'}
    directory = Path('output/acceptance'); directory.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
