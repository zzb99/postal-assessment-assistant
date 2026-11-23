from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from io import BytesIO
from pypdf import PdfWriter

from backend.app.main import app
from backend.app import governance
from backend.tests.test_assessment_workflow import reset_database


def test_one_time_device_trust_policy_approval_and_revoke(monkeypatch):
    reset_database()
    monkeypatch.setattr(governance, 'settings', replace(governance.settings, require_trusted_device=True, require_policy_approval=True))
    with TestClient(app) as client:
        auth = client.post('/api/auth/login', json={'username': 'admin', 'password': 'StrongPassw0rd!'}).json()
        admin = {'Authorization': 'Bearer ' + auth['access_token']}
        device = {'X-Device-Token': 'b' * 64}
        pending = client.post('/api/quick/device', headers=device, json={'team': '二班', 'name': '张三'})
        assert pending.status_code == 200 and pending.json()['status'] == 'pending'
        assert client.get('/api/governance/devices').status_code == 401
        row = client.get('/api/governance/devices', headers=admin).json()[0]
        assert row['team'] == '二班' and 'device_hash' not in row
        assert client.put(f"/api/governance/devices/{row['id']}", headers=admin, json={'approved': True, 'code': row['code']}).status_code == 200
        assert client.get('/api/quick/device', headers=device).json()['status'] == 'approved'
        policy = client.get('/api/governance/policy', headers=admin).json()
        assert policy['approval_status'] == 'legacy' and policy['version'] == '20260819'
        assert client.post('/api/governance/policy/approve', headers=admin, json={'digest': 'wrong'}).status_code == 409
        assert client.post('/api/governance/policy/approve', headers=admin, json={'digest': policy['digest']}).status_code == 200
        with governance.SessionLocal() as session:
            governance.require_formal_authority(session, governance.device_hash('b' * 64), '20260819', '2026-10-13')
        client.put(f"/api/governance/devices/{row['id']}", headers=admin, json={'approved': False, 'code': row['code']})
        assert client.get('/api/quick/device', headers=device).json()['status'] == 'revoked'
        # Public policy files must not be served by API as static resources.
        assert client.get('/production-quality-rules.json').status_code == 404


@pytest.mark.parametrize('device_state', ['unregistered', 'pending', 'revoked'])
def test_public_intake_generates_without_device_or_policy_approval(monkeypatch, device_state):
    from backend.app import documents
    from backend.app.db import SessionLocal
    from backend.app.models import TrustedDevice, PolicyApproval
    from sqlalchemy import select, func
    reset_database()
    monkeypatch.setattr(governance, 'settings', replace(governance.settings, require_trusted_device=True, require_policy_approval=True))
    def convert(_):
        output = BytesIO(); pdf = PdfWriter(); pdf.add_blank_page(width=595.28, height=841.89); pdf.write(output)
        return output.getvalue()
    monkeypatch.setattr(documents, 'convert_word_to_pdf', convert)
    if device_state != 'unregistered':
        with SessionLocal.begin() as session:
            session.add(TrustedDevice(device_hash=governance.device_hash('c' * 64), code='TEST1234', team='二班', name='张三', status=device_state))
    with TestClient(app) as client:
        body = dict(request_id=str(uuid4()), incident_date='2026-10-13', shift='白班', team='二班', inspector_name='张三',
                    assessment_unit_id=1, assessment_unit_name='华阳公司', quantity=1, penalty_amount='40', assessment_content='检查发现遗留邮件。')
        response = client.post('/api/quick/assessments', headers={'X-Device-Token': 'c' * 64}, json=body)
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'effective'
        with SessionLocal() as session:
            assert session.scalar(select(func.count()).select_from(PolicyApproval)) == 0
        assert client.get(f"/api/quick/assessments/{response.json()['id']}/documents/pdf", headers={'X-Device-Token': 'd' * 64}).status_code == 404
