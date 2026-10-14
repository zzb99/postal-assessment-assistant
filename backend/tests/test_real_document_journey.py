"""Opt-in real LibreOffice integration; isolated test DB and mocked, non-billable AI."""
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.app import ai_writing, governance
from backend.app.main import app
from backend.tests.test_assessment_workflow import reset_database

pytestmark = pytest.mark.skipif(os.getenv('RUN_REAL_DOCUMENT_TESTS') != 'true', reason='opt-in real LibreOffice test')


def test_authorized_two_phone_generation_archive_and_local_continuation(monkeypatch):
    reset_database()
    monkeypatch.setattr(governance, 'settings', replace(governance.settings, require_trusted_device=True, require_policy_approval=True))
    ai_writing.request_cache.clear(); calls = []
    def mock_chat(*args, **kwargs):
        calls.append(1)
        return {'ruleId': 'official-036', 'pricingId': 'p1', 'quantity': 1, 'conditionsSatisfied': False,
                'missingFields': ['unloading_completed', 'single_event'], 'finding': '南5卸车口发现1件遗留邮件',
                'rectification': '落实一车一清，作业结束后检查车厢及卸车区域，避免再次发生', 'confidence': 'medium'}
    monkeypatch.setattr(ai_writing, '_chat', mock_chat)
    with TestClient(app) as client:
        admin = {'Authorization': 'Bearer ' + client.post('/api/auth/login', json={'username': 'admin', 'password': 'StrongPassw0rd!'}).json()['access_token']}
        policy = client.get('/api/governance/policy', headers=admin).json()
        assert client.post('/api/governance/policy/approve', headers=admin, json={'digest': policy['digest']}).status_code == 200
        unit = client.get('/api/quick/config').json()['units'][0]
        forms = []
        for token, name in [('a' * 64, '张智博'), ('b' * 64, '李明')]:
            device = {'X-Device-Token': token}
            registration = client.post('/api/quick/device', headers=device, json={'team': '二班', 'name': name}).json()
            assert client.put(f"/api/governance/devices/{registration['id']}", headers=admin, json={'approved': True, 'code': registration['code']}).status_code == 200
            context = dict(incident_date='2026-10-13', shift='白班', assessment_unit_id=unit['id'])
            result = client.post('/api/quick/ai/compose', headers=device, json={**context, 'facts': '南5卸车口发现遗留邮件1件'}).json()
            assert not result['ready'] and '落实一车一清' in result['draft_content']
            selected = client.post('/api/quick/ai/select', headers=device, json={'continuation_token': result['continuation_token'], 'rule_id': 'official-036', 'pricing_id': 'p1'})
            assert selected.status_code == 200, selected.text
            result = selected.json()
            for answer in ('unloading_completed', 'single_event'):
                response = client.post('/api/quick/ai/continue', headers=device, json={'continuation_token': result['continuation_token'], 'answers': {answer: True}})
                assert response.status_code == 200, response.text
                result = response.json()
            assert result['ready'] and result['penalty_amount'] == '40'
            form = {**context, 'assessment_unit_name': unit['name'], 'team': '二班', 'inspector_name': name, 'quantity': 1,
                    'penalty_amount': '40', 'assessment_content': result['assessment_content'], 'ai_proposal': result['proposal_token'], 'request_id': str(uuid4())}
            forms.append((device, form))
        # Distinct devices do not share private cache entries; answers do not call AI.
        assert calls == [1, 1]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda args: client.post('/api/quick/assessments', headers=args[0], json=args[1]), forms))
        numbers = set()
        for response, (device, form) in zip(responses, forms):
            assert response.status_code == 200, response.text
            result = response.json(); numbers.add(result['assessment_no'])
            pdf = client.get(f"/api/quick/assessments/{result['id']}/documents/pdf", headers=device)
            word = client.get(f"/api/quick/assessments/{result['id']}/documents/word", headers=device)
            assert pdf.status_code == word.status_code == 200
            reader = PdfReader(BytesIO(pdf.content)); text = reader.pages[0].extract_text()
            assert len(reader.pages) == 1 and '40' in text and '检查人' in text
            assert client.post('/api/quick/assessments', headers=device, json=form).json()['assessment_no'] == result['assessment_no']
            wrong = {'X-Device-Token': 'e' * 64}
            assert client.get(f"/api/quick/assessments/{result['id']}/documents/pdf", headers=wrong).status_code == 404
        assert len(numbers) == 2
