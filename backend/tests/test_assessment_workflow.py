import os
import shutil
from io import BytesIO
from pathlib import Path
import zipfile

Path(".pytest_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("DATABASE_URL", "sqlite:///./.pytest_cache/backend-test.sqlite")
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-must-be-at-least-32-bytes")
os.environ.setdefault("DOCUMENT_ROOT", str((Path(".pytest_cache") / "documents").resolve()))

from fastapi.testclient import TestClient
import pytest
from pypdf import PdfWriter

from backend.app import documents
from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import Assessment, AssessmentDocument, User
from backend.app.security import hash_password
from backend.app.seed import seed_reference_data


def reset_database() -> None:
    shutil.rmtree(Path(os.environ["DOCUMENT_ROOT"]), ignore_errors=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        seed_reference_data(session)
        session.add(User(username="admin", display_name="管理员", password_hash=hash_password("StrongPassw0rd!"), role="admin"))


@pytest.fixture(autouse=True)
def fake_libreoffice(monkeypatch):
    def convert(_: bytes) -> bytes:
        output = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=595.28, height=841.89)
        writer.write(output)
        return output.getvalue()
    monkeypatch.setattr(documents, "convert_word_to_pdf", convert)


def test_draft_finalize_copy_and_statistics() -> None:
    reset_database()
    with TestClient(app) as client:
        token = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassw0rd!"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        reference = client.get("/api/management/reference-data", headers=headers).json()
        unit = reference["units"][0]
        created = client.post("/api/assessments", headers=headers, json={
            "incident_date": "2026-08-21", "shift": "白班", "team": "一班", "assessment_unit_id": unit["id"], "assessment_unit_name": unit["name"],
            "inspector_name": "吴正一", "quantity": 2, "assessment_content": "错发邮件，已现场核实。", "penalty_amount": "100", "remark": "保留格式\n第二行",
        })
        assert created.status_code == 201
        draft = created.json()
        assert draft["status"] == "draft"
        assert draft["assessment_no"] is None
        assert draft["penalty_amount_cn"] == "壹佰元整"

        finalized = finalize_record(client, draft["id"], headers)
        assert finalized.status_code == 200
        assert finalized.json()["assessment_no"] == "KH-202608-0001"
        assert finalized.json()["status"] == "effective"

        word = client.get(f"/api/assessments/{draft['id']}/documents/word", headers=headers)
        pdf = client.get(f"/api/assessments/{draft['id']}/documents/pdf", headers=headers)
        assert word.status_code == 200 and word.content[:2] == b"PK"
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
        with zipfile.ZipFile(BytesIO(word.content)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        assert "华阳公司" in xml
        assert "一班吴正一" in xml
        assert "壹佰元整" in xml
        assert "{{" not in xml
        # Filling fields must preserve the supplied template's paragraph formatting.
        from lxml import etree
        root = etree.fromstring(xml.encode())
        namespace = {"w": documents.W_NS}
        from backend.app.config import settings
        with zipfile.ZipFile(settings.document_template) as original:
            template_root = etree.fromstring(original.read("word/document.xml"))
        assert [etree.tostring(p) for p in root.findall('.//w:pPr', namespace)] == [etree.tostring(p) for p in template_root.findall('.//w:pPr', namespace)]
        excel = client.get("/api/exports/assessment-ledger.xlsx", headers=headers)
        assert excel.status_code == 200 and excel.content[:2] == b"PK"

        copied = client.post(f"/api/assessments/{draft['id']}/copy", headers=headers)
        assert copied.status_code == 201
        assert copied.json()["status"] == "draft"
        assert copied.json()["assessment_no"] is None

        overview = client.get("/api/statistics/overview?today=2026-08-21", headers=headers)
        assert overview.status_code == 200
        assert overview.json()["month_count"] == 1
        assert overview.json()["month_amount"] == "100.00"


def test_management_rbac_scope_and_draft_update() -> None:
    reset_database()
    with TestClient(app) as client:
        admin_token = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassw0rd!"}).json()["access_token"]
        admin = {"Authorization": f"Bearer {admin_token}"}
        first_department = client.get("/api/management/reference-data", headers=admin).json()["departments"][0]
        second_department = client.post("/api/management/departments", headers=admin, json={"name": "外部协作部门"}).json()
        second_unit = client.post("/api/management/units", headers=admin, json={"name": "外部测试单位", "department_id": second_department["id"]}).json()
        manager = client.post("/api/management/users", headers=admin, json={
            "username": "dept.manager", "display_name": "部门主管", "password": "ManagerPassw0rd!", "role": "department_manager", "department_id": first_department["id"],
        })
        assert manager.status_code == 201
        leader = client.post("/api/management/users", headers=admin, json={
            "username": "leader", "display_name": "领导", "password": "LeaderPassw0rd!", "role": "leader", "department_id": None,
        })
        assert leader.status_code == 201
        assert client.post("/api/management/users", headers=admin, json={
            "username": "leader", "display_name": "重复", "password": "LeaderPassw0rd!", "role": "leader", "department_id": None,
        }).status_code == 409

        manager_token = client.post("/api/auth/login", json={"username": "dept.manager", "password": "ManagerPassw0rd!"}).json()["access_token"]
        manager_headers = {"Authorization": f"Bearer {manager_token}"}
        manager_reference = client.get("/api/management/reference-data", headers=manager_headers).json()
        assert all(unit["department_id"] == first_department["id"] for unit in manager_reference["units"])
        forbidden = client.post("/api/assessments", headers=manager_headers, json={
            "incident_date": "2026-08-22", "shift": "白班", "team": "一班", "assessment_unit_id": second_unit["id"], "assessment_unit_name": second_unit["name"],
            "inspector_name": "吴正一", "quantity": 1, "assessment_content": "不应允许跨部门建单", "penalty_amount": "10",
        })
        assert forbidden.status_code == 403

        own_unit = manager_reference["units"][0]
        draft = client.post("/api/assessments", headers=manager_headers, json={
            "incident_date": "2026-08-22", "shift": "白班", "team": "一班", "assessment_unit_id": own_unit["id"], "assessment_unit_name": own_unit["name"],
            "inspector_name": "吴正一", "quantity": 1, "assessment_content": "初始草稿", "penalty_amount": "10",
        }).json()
        updated = client.put(f"/api/assessments/{draft['id']}", headers=manager_headers, json={
            "incident_date": "2026-08-22", "shift": "夜班", "team": "二班", "assessment_unit_id": own_unit["id"], "assessment_unit_name": own_unit["name"],
            "inspector_name": "黄旭东", "quantity": 3, "assessment_content": "最后一次保存内容", "penalty_amount": "12", "updated_at": draft["updated_at"],
        })
        assert updated.status_code == 200
        formal = finalize_record(client, draft["id"], manager_headers).json()
        assert formal["assessment_content"] == "最后一次保存内容"
        assert formal["penalty_amount"] == "12.00"
        assert client.delete(f"/api/assessments/{draft['id']}", headers=admin).status_code == 405

        leader_token = client.post("/api/auth/login", json={"username": "leader", "password": "LeaderPassw0rd!"}).json()["access_token"]
        leader_headers = {"Authorization": f"Bearer {leader_token}"}
        assert client.get("/api/assessments", headers=leader_headers).status_code == 200
        assert client.post("/api/assessments", headers=leader_headers, json={}).status_code == 403


@pytest.mark.parametrize("quantity,amount", [(0, "100"), (-1, "100"), (1.5, "100"), (1, "0"), (1, "-10"), (1, "10.5")])
def test_invalid_quantity_and_amount_cannot_be_saved(quantity, amount) -> None:
    reset_database()
    with TestClient(app) as client:
        token = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassw0rd!"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        unit = client.get("/api/management/reference-data", headers=headers).json()["units"][0]
        response = client.post("/api/assessments", headers=headers, json={
            "incident_date": "2026-09-06", "shift": "白班", "team": "一班", "assessment_unit_id": unit["id"], "assessment_unit_name": unit["name"],
            "inspector_name": "吴正一", "quantity": quantity, "assessment_content": "校验测试", "penalty_amount": amount,
        })
        assert response.status_code == 422


def test_free_team_and_inspector_are_normalized_without_roster() -> None:
    reset_database()
    with TestClient(app) as client:
        token = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassw0rd!"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        unit = client.get("/api/management/reference-data", headers=headers).json()["units"][0]
        response = client.post("/api/assessments", headers=headers, json={
            "incident_date": "2026-09-06", "shift": "白班", "team": "  ２ 班  ", "assessment_unit_id": unit["id"], "assessment_unit_name": unit["name"],
            "inspector_name": " 张 三 ", "quantity": 1, "assessment_content": "班组人员自由填报", "penalty_amount": "100",
        })
        assert response.status_code == 201
        assert response.json()["team"] == "二班"
        assert response.json()["inspector_name"] == "张三"


def quick_payload(unit, request_id="30258602-3408-4f54-b31f-08f64d31951d"):
    return {**draft_payload(unit), "team": " 2 班 ", "inspector_name": "张 三", "request_id": request_id}


def test_quick_anonymous_generate_archive_and_private_device_history():
    reset_database()
    device = {"X-Device-Token": "a" * 64}
    other = {"X-Device-Token": "b" * 64}
    with TestClient(app) as client:
        refs = client.get("/api/quick/config")
        assert refs.status_code == 200
        assert set(refs.json()) == {"units", "shifts", "ai_enabled", "regulation_version"}
        unit = refs.json()["units"][0]
        assert client.post("/api/quick/assessments", json=quick_payload(unit)).status_code == 401
        response = client.post("/api/quick/assessments", headers=device, json=quick_payload(unit))
        assert response.status_code == 200
        item = response.json()
        assert item["status"] == "effective" and item["assessment_no"] == "KH-202610-0001"
        assert item["team"] == "二班" and item["inspector_name"] == "张三"
        assert client.get("/api/quick/assessments", headers=device).json()["total"] == 1
        assert client.get("/api/quick/assessments", headers=other).json()["total"] == 0
        for kind, signature in (("word", b"PK"), ("pdf", b"%PDF")):
            file = client.get(f"/api/quick/assessments/{item['id']}/documents/{kind}", headers=device)
            assert file.status_code == 200 and file.content.startswith(signature)
            assert "no-store" in file.headers["cache-control"]
            assert client.get(f"/api/quick/assessments/{item['id']}/documents/{kind}", headers=other).status_code == 404
        assert client.get(f"/api/assessments/{item['id']}", headers=device).status_code == 401
        assert client.post(f"/api/assessments/{item['id']}/void", headers=device, json={"reason": "匿名越权"}).status_code == 401
        admin = login_headers(client)
        assert client.get("/api/assessments", headers=admin).json()["total"] == 1
        assert client.get("/api/statistics/teams", headers=admin).json()[0]["name"] == "二班"
        assert client.get("/api/statistics/inspectors", headers=admin).json()[0]["name"] == "张三"
        assert client.get("/api/statistics/teams").status_code == 401


def test_quick_idempotency_and_conflicting_reuse():
    reset_database()
    with TestClient(app) as client:
        unit = client.get("/api/quick/config").json()["units"][0]
        headers = {"X-Device-Token": "c" * 64}
        payload = quick_payload(unit)
        first = client.post("/api/quick/assessments", headers=headers, json=payload)
        assert first.status_code == 200
        retry = client.post("/api/quick/assessments", headers=headers, json=payload)
        assert retry.status_code == 200 and retry.json()["id"] == first.json()["id"]
        assert client.post("/api/quick/assessments", headers=headers, json={**payload, "penalty_amount": "200"}).status_code == 409
        with SessionLocal() as session:
            assert session.query(Assessment).count() == 1
            assert session.query(AssessmentDocument).count() == 1


def test_quick_failed_conversion_retries_same_draft(monkeypatch):
    reset_database()
    real_mock = documents.convert_word_to_pdf
    def fail(_: bytes):
        raise documents.DocumentGenerationError("测试转换失败")
    with TestClient(app) as client:
        unit = client.get("/api/quick/config").json()["units"][0]
        headers = {"X-Device-Token": "d" * 64}
        monkeypatch.setattr(documents, "convert_word_to_pdf", fail)
        response = client.post("/api/quick/assessments", headers=headers, json=quick_payload(unit))
        assert response.status_code == 503
        with SessionLocal() as session:
            draft = session.query(Assessment).one()
            draft_id = draft.id
            assert draft.status == "draft" and draft.assessment_no is None
            assert session.query(AssessmentDocument).count() == 0
        monkeypatch.setattr(documents, "convert_word_to_pdf", real_mock)
        retry = client.post("/api/quick/assessments", headers=headers, json=quick_payload(unit))
        assert retry.status_code == 200 and retry.json()["id"] == draft_id


def test_quick_lock_refreshes_after_draft_commit(monkeypatch):
    from sqlalchemy import update
    from backend.app.routers import quick as quick_router
    reset_database()
    class InterleavedSlot:
        def acquire(self, *, timeout=45):
            with SessionLocal.begin() as other_session:
                other_session.execute(update(Assessment).values(assessment_content="另一个已授权请求修改的内容"))
            return True
        def release(self):
            pass
    monkeypatch.setattr(quick_router, "generation_slot", InterleavedSlot())
    with TestClient(app) as client:
        unit = client.get("/api/quick/config").json()["units"][0]
        response = client.post("/api/quick/assessments", headers={"X-Device-Token": "f" * 64}, json=quick_payload(unit))
        assert response.status_code == 200
        assert response.json()["assessment_content"] == "另一个已授权请求修改的内容"


def test_quick_body_limit_and_generation_busy(monkeypatch):
    from backend.app.routers import quick as quick_router
    reset_database()
    class BusySlot:
        def acquire(self, *, timeout=45):
            return False
    monkeypatch.setattr(quick_router, "generation_slot", BusySlot())
    with TestClient(app) as client:
        headers = {"X-Device-Token": "1" * 64}
        assert client.post("/api/quick/assessments", headers=headers, content=b" " * 17000).status_code == 413
        unit = client.get("/api/quick/config").json()["units"][0]
        assert client.post("/api/quick/assessments", headers=headers, json=quick_payload(unit)).status_code == 429


def test_quick_limiter_is_bounded():
    from backend.app.quick import IntakeLimiter
    from fastapi import HTTPException
    guard = IntakeLimiter()
    guard.check("test", 1)
    with pytest.raises(HTTPException) as error:
        guard.check("test", 1)
    assert error.value.status_code == 429


@pytest.mark.parametrize("change", [{"team": "  "}, {"inspector_name": " "}, {"quantity": 0}, {"penalty_amount": "0"}, {"penalty_amount": "1.5"}, {"status": "effective"}, {"created_by": 1}, {"department_id": 1}])
def test_quick_invalid_or_privilege_fields_rejected(change):
    reset_database()
    with TestClient(app) as client:
        unit = client.get("/api/management/reference-data", headers=login_headers(client)).json()["units"][0]
        response = client.post("/api/quick/assessments", headers={"X-Device-Token": "e" * 64}, json={**quick_payload(unit), **change})
        assert response.status_code == 422


def test_conversion_failure_keeps_record_as_draft(monkeypatch) -> None:
    reset_database()
    with TestClient(app) as client:
        token = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassw0rd!"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        unit = client.get("/api/management/reference-data", headers=headers).json()["units"][0]
        draft = client.post("/api/assessments", headers=headers, json={
            "incident_date": "2026-09-06", "shift": "白班", "team": "一班", "assessment_unit_id": unit["id"], "assessment_unit_name": unit["name"],
            "inspector_name": "吴正一", "quantity": 1, "assessment_content": "转换失败回滚测试", "penalty_amount": "100",
        }).json()

        def fail(_: bytes) -> bytes:
            raise documents.DocumentGenerationError("模拟转换失败")
        monkeypatch.setattr(documents, "convert_word_to_pdf", fail)
        response = finalize_record(client, draft["id"], headers)
        assert response.status_code == 503
        with SessionLocal() as session:
            assessment = session.get(Assessment, draft["id"])
            assert assessment is not None and assessment.status == "draft" and assessment.assessment_no is None
            assert session.query(AssessmentDocument).count() == 0


def login_headers(client, username="admin", password="StrongPassw0rd!"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def finalize_record(client, assessment_id, headers):
    record = client.get(f"/api/assessments/{assessment_id}", headers=headers).json()
    return client.post(f"/api/assessments/{assessment_id}/finalize", headers=headers, json={"updated_at": record["updated_at"]})


def draft_payload(unit):
    return {
        "incident_date": "2026-10-09", "shift": "白班", "team": "一班",
        "assessment_unit_id": unit["id"], "assessment_unit_name": unit["name"],
        "inspector_name": "吴正一", "quantity": 1,
        "assessment_content": "职工现场检查填报", "penalty_amount": "100",
    }


def employee_setup(client):
    admin = login_headers(client)
    refs = client.get("/api/management/reference-data", headers=admin).json()
    department = refs["departments"][0]["id"]
    # Direct fixture setup permits checking IDOR even before employee creation is implemented.
    with SessionLocal.begin() as session:
        for name, role in (("employee.one", "employee"), ("employee.two", "employee"), ("supervisor", "department_manager")):
            session.add(User(username=name, display_name=name, role=role, department_id=department, password_hash=hash_password("StrongPassw0rd!")))
    return admin, login_headers(client, "employee.one"), login_headers(client, "employee.two"), login_headers(client, "supervisor"), refs["units"][0]


def test_employee_account_requires_department_and_supports_updates():
    reset_database()
    with TestClient(app) as client:
        admin = login_headers(client)
        dept = client.get("/api/management/reference-data", headers=admin).json()["departments"][0]["id"]
        payload = {"username": "staff", "display_name": "职工", "password": "StrongPassw0rd!", "role": "employee", "department_id": dept}
        created = client.post("/api/management/users", headers=admin, json=payload)
        assert created.status_code == 201
        assert client.post("/api/management/users", headers=admin, json={**payload, "username": "unbound", "department_id": None}).status_code == 422
        update = {"display_name": "职工改名", "role": "employee", "department_id": dept, "active": True}
        assert client.put(f"/api/management/users/{created.json()['id']}", headers=admin, json=update).status_code == 200
        assert client.put(f"/api/management/users/{created.json()['id']}", headers=admin, json={**update, "department_id": None}).status_code == 422


def test_employee_own_drafts_and_supervisor_finalize_workflow():
    reset_database()
    with TestClient(app) as client:
        admin, employee, other, supervisor, unit = employee_setup(client)
        payload = draft_payload(unit)
        response = client.post("/api/assessments", headers=employee, json=payload)
        assert response.status_code == 201
        draft = response.json()
        assert client.put(f"/api/assessments/{draft['id']}", headers=employee, json={**payload, "assessment_content": "职工修改草稿", "updated_at": draft["updated_at"]}).status_code == 200
        assert client.post(f"/api/assessments/{draft['id']}/copy", headers=employee).status_code == 201
        assert finalize_record(client, draft["id"], employee).status_code == 403
        assert client.put(f"/api/assessments/{draft['id']}", headers=other, json={**payload, "updated_at": draft["updated_at"]}).status_code == 403
        assert client.get("/api/assessments", headers=other).json()["total"] == 0
        assert client.get("/api/assessments", headers=supervisor).json()["total"] == 2
        reviewed = client.get(f"/api/assessments/{draft['id']}", headers=supervisor).json()
        assert client.put(f"/api/assessments/{draft['id']}", headers=supervisor, json={**payload, "assessment_content": "主管复核内容", "updated_at": reviewed["updated_at"]}).status_code == 200
        formal = finalize_record(client, draft["id"], supervisor)
        assert formal.status_code == 200
        assert formal.json()["assessment_content"] == "主管复核内容"
        assert client.get(f"/api/assessments/{draft['id']}/documents/pdf", headers=employee).status_code == 200
        assert client.get(f"/api/assessments/{draft['id']}/documents/pdf", headers=other).status_code == 403
        assert client.post(f"/api/assessments/{draft['id']}/void", headers=employee, json={"reason": "非法作废"}).status_code == 403
        assert client.post(f"/api/assessments/{draft['id']}/void", headers=supervisor, json={"reason": "主管复核作废"}).status_code == 200


def test_employee_cannot_enumerate_other_records_or_management_data():
    reset_database()
    with TestClient(app) as client:
        admin, employee, _, supervisor, unit = employee_setup(client)
        draft = client.post("/api/assessments", headers=admin, json=draft_payload(unit)).json()
        assert client.get("/api/assessments", headers=employee).json()["total"] == 0
        for path in (f"/api/assessments/{draft['id']}", f"/api/assessments/{draft['id']}/documents/word", f"/api/assessments/{draft['id']}/documents/pdf", "/api/management/users", "/api/management/catalog", "/api/exports/assessment-ledger.xlsx", "/api/statistics/units", "/api/statistics/departments", "/api/statistics/categories"):
            assert client.get(path, headers=employee).status_code == 403, path
        assert client.post(f"/api/assessments/{draft['id']}/copy", headers=employee).status_code == 403
        other_dept = client.post("/api/management/departments", headers=admin, json={"name": "其他部门"}).json()
        outside = client.post("/api/management/units", headers=admin, json={"name": "跨部门单位", "department_id": other_dept["id"]}).json()
        assert client.post("/api/assessments", headers=employee, json=draft_payload(outside)).status_code == 403
        outside_draft = client.post("/api/assessments", headers=admin, json=draft_payload(outside)).json()
        assert client.post(f"/api/assessments/{outside_draft['id']}/void", headers=supervisor, json={"reason": "跨部门作废"}).status_code == 403
        refs = client.get("/api/management/reference-data", headers=employee).json()
        assert all(item["department_id"] == unit["department_id"] for item in refs["units"])


def test_employee_overview_excludes_colleagues_and_unknown_roles_fail_closed():
    reset_database()
    with TestClient(app) as client:
        admin, employee, _, _, unit = employee_setup(client)
        draft = client.post("/api/assessments", headers=admin, json=draft_payload(unit)).json()
        assert finalize_record(client, draft["id"], admin).status_code == 200
        assert client.get("/api/statistics/overview?today=2026-10-09", headers=employee).json()["month_count"] == 0
        with SessionLocal.begin() as session:
            session.add(User(username="unknown", display_name="未知角色", role="invalid-role", password_hash=hash_password("StrongPassw0rd!")))
        unknown = login_headers(client, "unknown")
        assert client.get("/api/assessments", headers=unknown).status_code == 403


def test_ai_status_exposes_availability_not_secret():
    reset_database()
    with TestClient(app) as client:
        assert client.get("/api/ai/status").status_code == 401
        response = client.get("/api/ai/status", headers=login_headers(client))
        assert response.status_code == 200
        assert set(response.json()) == {"enabled", "model", "max_tokens"}
        assert response.json()['model'] == 'deepseek-flash'
        assert response.json()['max_tokens'] == 900
        assert isinstance(response.json()["enabled"], bool)


def test_same_second_updates_have_distinct_versions():
    from datetime import datetime, timezone
    from backend.app.routers.assessments import comparable_timestamp
    first = datetime(2026, 10, 9, 12, 0, 0, 100000, tzinfo=timezone.utc)
    second = first.replace(microsecond=900000)
    assert comparable_timestamp(first) != comparable_timestamp(second)


def test_finalize_must_use_supervisor_reviewed_version():
    reset_database()
    with TestClient(app) as client:
        _, employee, _, supervisor, unit = employee_setup(client)
        payload = draft_payload(unit)
        draft = client.post("/api/assessments", headers=employee, json=payload).json()
        updated = client.put(f"/api/assessments/{draft['id']}", headers=employee, json={**payload, "updated_at": draft["updated_at"], "assessment_content": "员工再次修改"}).json()
        assert client.post(f"/api/assessments/{draft['id']}/finalize", headers=supervisor, json={"updated_at": draft["updated_at"]}).status_code == 409
        assert client.post(f"/api/assessments/{draft['id']}/finalize", headers=supervisor).status_code == 422
        assert client.post(f"/api/assessments/{draft['id']}/finalize", headers=supervisor, json={"updated_at": updated["updated_at"]}).status_code == 200
        assert client.put(f"/api/assessments/{draft['id']}", headers=employee, json={**payload, "updated_at": updated["updated_at"]}).status_code == 409


def test_excel_treats_employee_text_as_literal_not_formula():
    from openpyxl import load_workbook
    reset_database()
    with TestClient(app) as client:
        _, employee, _, supervisor, unit = employee_setup(client)
        payload = {**draft_payload(unit), "assessment_content": '=HYPERLINK("https://example.invalid", "问题")', "remark": "=2+2", "operation_stage": "=2+2"}
        assert client.post("/api/assessments", headers=employee, json=payload).status_code == 201
        exported = client.get("/api/exports/assessment-ledger.xlsx", headers=supervisor)
        workbook = load_workbook(BytesIO(exported.content), data_only=False)
        for column in ("H2", "N2", "O2"):
            assert workbook["考核台账"][column].data_type == "s", column
        assert workbook["考核台账"]["N2"].value == payload["assessment_content"]


def test_old_token_obeys_role_changes_and_department_changes():
    reset_database()
    with TestClient(app) as client:
        admin, employee, _, supervisor, unit = employee_setup(client)
        draft = client.post("/api/assessments", headers=admin, json=draft_payload(unit)).json()
        assert client.get(f"/api/assessments/{draft['id']}", headers=supervisor).status_code == 200
        from sqlalchemy import select
        with SessionLocal.begin() as session:
            account = session.scalar(select(User).where(User.username == "supervisor"))
            account.role = "employee"
        assert client.get(f"/api/assessments/{draft['id']}", headers=supervisor).status_code == 403
        assert client.get("/api/exports/assessment-ledger.xlsx", headers=supervisor).status_code == 403
        with SessionLocal.begin() as session:
            account = session.scalar(select(User).where(User.username == "employee.one"))
            account.department_id = None
        assert client.get("/api/assessments", headers=employee).status_code == 403
