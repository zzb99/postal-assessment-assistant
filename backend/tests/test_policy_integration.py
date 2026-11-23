"""Full HTTP policy permissions, persistence, failure compensation and tariffs."""
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path
import json

import pytest
from docx import Document
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import ai_writing, policy_store
from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.models import AuditLog, Department, User
from backend.app.policy_pricing import simple_tariff
from backend.app.pricing import calculate
from backend.app.rule_search import get_index
from backend.app.security import hash_password
from backend.tests.test_assessment_workflow import reset_database

WORD = next(Path(__file__).resolve().parents[2].glob('*20260819.docx')).read_bytes()


@pytest.fixture
def policy_client(tmp_path, monkeypatch):
    reset_database()
    monkeypatch.setattr(policy_store, 'settings', replace(policy_store.settings, document_root=tmp_path))
    ai_writing.request_cache.clear()
    with SessionLocal.begin() as db:
        department = db.scalar(select(Department))
        for role in ('department_manager', 'employee', 'leader'):
            db.add(User(username=role, display_name=role, password_hash=hash_password('SyntheticOnly2026!'), role=role, department_id=department.id))
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = {}
        for role in ('admin', 'department_manager', 'employee', 'leader'):
            password = 'StrongPassw0rd!' if role == 'admin' else 'SyntheticOnly2026!'
            token = client.post('/api/auth/login', json={'username': role, 'password': password}).json()['access_token']
            headers[role] = {'Authorization': 'Bearer ' + token}
        yield client, headers


def upload(client, headers, version='TEST-ONE', content=WORD, effective='2026-08-19', route='publish'):
    return client.post('/api/policies/' + route, headers=headers, data={'version': version, 'effective_date': effective, 'allow_major_change': 'true'}, files={'file': ('通则.docx', content, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})


@pytest.mark.parametrize('role,code', [('admin', 200), ('department_manager', 200), ('employee', 403), ('leader', 403)])
def test_policy_http_role_matrix(policy_client, role, code):
    client, headers = policy_client
    preview = upload(client, headers[role], route='preview')
    assert preview.status_code == code, preview.text
    if code == 200:
        assert preview.json()['diff']['summary']['unchanged'] >= 8
        assert policy_store.manifest()['versions'] == []
    published = upload(client, headers[role])
    assert published.status_code == code, published.text
    assert client.get('/api/policies/versions', headers=headers[role]).status_code == code
    if code == 200:
        policy_id = policy_store.manifest()['current']
        for tested_role, expected in [('admin', 200), ('department_manager', 200), ('employee', 403), ('leader', 403)]:
            response = client.get(f'/api/policies/{policy_id}/original', headers=headers[tested_role])
            assert response.status_code == expected
            if expected == 200: assert response.content == WORD
            assert client.post(f'/api/policies/{policy_id}/restore', headers=headers[tested_role]).status_code == expected
        assert get_index().catalog['version'] == 'TEST-ONE'
        with SessionLocal() as db:
            assert db.scalar(select(AuditLog).where(AuditLog.action == 'policy.publish')) is not None


def test_anonymous_cannot_publish_but_can_load_mobile_config(policy_client):
    client, _ = policy_client
    assert upload(client, {}).status_code == 401
    response = client.get('/api/quick/config')
    assert response.status_code == 200 and response.json()['units']


def test_chinese_version_download_and_duplicate_rejected(policy_client):
    client, headers = policy_client
    assert upload(client, headers['department_manager'], version='通则-新版').status_code == 200
    policy_id = policy_store.manifest()['current']
    response = client.get(f'/api/policies/{policy_id}/original', headers=headers['department_manager'])
    assert response.status_code == 200 and response.content == WORD
    assert upload(client, headers['admin'], version='通则-新版').status_code == 422


def test_restore_does_not_change_yesterdays_policy(policy_client):
    client, headers = policy_client
    assert upload(client, headers['admin']).status_code == 200
    first = policy_store.manifest()['current']
    assert upload(client, headers['department_manager'], version='TEST-TWO', effective='2026-09-01').status_code == 200
    assert get_index(date(2026, 10, 13)).catalog['version'] == 'TEST-TWO'
    assert client.post(f'/api/policies/{first}/restore', headers=headers['department_manager']).status_code == 200
    assert get_index(date(2026, 10, 13)).catalog['version'] == 'TEST-TWO'
    assert get_index(date(2026, 10, 15)).catalog['version'] == 'TEST-ONE'


@pytest.mark.parametrize('action', ['publish', 'restore'])
def test_failed_audit_restores_exact_manifest(policy_client, monkeypatch, action):
    from backend.app.routers import policies
    client, headers = policy_client
    assert upload(client, headers['admin']).status_code == 200
    first = policy_store.manifest()['current']
    assert upload(client, headers['admin'], version='TEST-TWO').status_code == 200
    if action == 'publish':
        assert client.post(f'/api/policies/{first}/restore', headers=headers['admin']).status_code == 200
    before = policy_store.manifest()
    def fail(*args, **kwargs):
        raise RuntimeError('simulated audit failure')
    monkeypatch.setattr(policies, 'write_audit_log', fail)
    response = upload(client, headers['admin'], version='TEST-THREE') if action == 'publish' else client.post(f'/api/policies/{first}/restore', headers=headers['admin'])
    assert response.status_code == 500
    assert policy_store.manifest() == before
    assert not (policy_store.root() / 'pending.json').exists()


@pytest.mark.parametrize('text,kind,price', [
    ('邮件未按规定摆放，每件考核20元。', 'per_piece', 20),
    ('未完成现场检查，每次处罚100元。', 'per_event', 100),
    ('违规占用消防通道，定额考核300元。', 'fixed', 300),
    ('邮件未按规定摆放，考核20元/件。', 'per_piece', 20),
])
def test_simple_local_tariff_grammar(text, kind, price):
    option = simple_tariff(text)
    assert option['billingType'] == kind and option['unitPrice'] == price
    assert option['autoApproved'] is False


@pytest.mark.parametrize('text', [
    '未执行检查，每次考核100-200元。', '未执行检查，每次100元，重复加倍。',
    '未执行检查，每次100元，同时考核负责人50元。', '未执行检查，视情考核100元。',
    '邮件超过2小时未清理，每件20元。', '每次处罚100元。', '未执行检查，罚款100元，另行处理。',
])
def test_complex_tariff_stays_manual(text):
    assert simple_tariff(text) is None


def test_new_tariff_publish_auto_arithmetic_and_amendment_stays_manual(policy_client):
    client, headers = policy_client
    document = Document(BytesIO(WORD))
    document.add_paragraph('二、卸车环节')
    document.add_paragraph('邮件未按规定摆放，每件考核20元。')
    content = BytesIO(); document.save(content)
    assert upload(client, headers['admin'], content=content.getvalue()).status_code == 200
    rule = next(r for r in get_index().rules if r['original'] == '邮件未按规定摆放，每件考核20元。')
    result = calculate(rule, 'simple-1', '发现未摆放邮件3件', 3, {'clause_applies': True})
    assert result['ready'] and result['amount'] == 60
    assert not calculate(rule, 'simple-1', '发现邮件3件', 3, {'clause_applies': False})['ready']
    document.paragraphs[-1].text = '邮件未按规定摆放，每件考核30元。'
    revised = BytesIO(); document.save(revised)
    assert upload(client, headers['department_manager'], version='AMENDED', content=revised.getvalue()).status_code == 200
    changed = next(r for r in get_index().rules if r['original'] == '邮件未按规定摆放，每件考核30元。')
    assert not any(p.get('autoApproved') for p in changed['pricingOptions'])
    assert any(r['amount_changed'] for r in get_index().catalog['diff']['changes'])


def test_duplicate_paragraphs_and_table_rows_are_not_lost():
    document = Document(BytesIO(WORD))
    document.add_paragraph('重复的核查记录应保留以便溯源。')
    document.add_paragraph('重复的核查记录应保留以便溯源。')
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = '附表现场问题'
    table.cell(0, 1).text = '按原文核实，不自动定价。'
    content = BytesIO(); document.save(content)
    parsed = policy_store.parse_word(content.getvalue(), version='TABLE', effective_date='2026-10-14', filename='test.docx')
    assert sum(r['original'] == '重复的核查记录应保留以便溯源。' for r in parsed['rules']) == 2
    assert parsed['rules'][-1]['sourceLocation']['kind'] == 'table'
    assert '附表现场问题' in parsed['rules'][-1]['original']


def test_cached_interpretation_cannot_cross_policy_change(monkeypatch):
    from backend.tests.test_ai_optimization import payload, raw
    index = get_index()
    entry = {'catalog_digest': 'different-catalog', 'raw': raw(), 'candidates': []}
    with pytest.raises(HTTPException) as err:
        ai_writing._evaluate(entry, payload(), 'unused', 'test')
    assert err.value.status_code == 409


@pytest.mark.parametrize('committed', [False, True])
def test_restart_recovers_interrupted_policy_transaction(policy_client, committed):
    from backend.app.audit import write_audit_log
    client, headers = policy_client
    assert upload(client, headers['admin']).status_code == 200
    before = policy_store.manifest()
    assert upload(client, headers['admin'], version='SECOND').status_code == 200
    after = policy_store.manifest()
    operation = 'synthetic-interrupted-operation'
    if committed:
        with SessionLocal.begin() as db:
            admin = db.scalar(select(User).where(User.username == 'admin'))
            write_audit_log(db, operator_id=admin.id, action='policy.commit', target_type='policy_operation', target_id=operation)
    pending = {'operation': operation, 'before': before, 'after': after}
    (policy_store.root() / 'pending.json').write_text(json.dumps(pending), encoding='utf-8')
    assert policy_store.manifest() == (after if committed else before)
    assert not (policy_store.root() / 'pending.json').exists()


def test_disk_write_failure_keeps_existing_policy(policy_client, monkeypatch):
    client, headers = policy_client
    assert upload(client, headers['admin']).status_code == 200
    before = policy_store.manifest()
    original_write = policy_store._atomic_write
    def fail(path, content):
        if path.suffix == '.docx': raise OSError('simulated full/read-only disk')
        original_write(path, content)
    monkeypatch.setattr(policy_store, '_atomic_write', fail)
    assert upload(client, headers['admin'], version='DISK-FAIL').status_code == 500
    assert policy_store.manifest() == before

