import os
from pathlib import Path

Path(".pytest_cache").mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///./.pytest_cache/backend-test.sqlite"
os.environ["JWT_SECRET"] = "test-only-jwt-secret-must-be-at-least-32-bytes"

from fastapi.testclient import TestClient

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import User
from backend.app.security import hash_password
from backend.app.seed import seed_reference_data


def reset_database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        seed_reference_data(session)
        session.add(User(username="admin", display_name="管理员", password_hash=hash_password("StrongPassw0rd!"), role="admin"))


def test_draft_finalize_copy_and_statistics() -> None:
    reset_database()
    with TestClient(app) as client:
        token = client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassw0rd!"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        reference = client.get("/api/management/reference-data", headers=headers).json()
        unit = reference["units"][0]
        created = client.post("/api/assessments", headers=headers, json={
            "incident_date": "2026-08-21", "shift": "白班", "assessment_unit_id": unit["id"], "assessment_unit_name": unit["name"],
            "inspector_name": "检查人", "assessment_content": "错发邮件，已现场核实。", "penalty_amount": "0.50", "remark": "保留格式\n第二行",
        })
        assert created.status_code == 201
        draft = created.json()
        assert draft["status"] == "draft"
        assert draft["assessment_no"] is None
        assert draft["penalty_amount_cn"] == "零元伍角"

        finalized = client.post(f"/api/assessments/{draft['id']}/finalize", headers=headers)
        assert finalized.status_code == 200
        assert finalized.json()["assessment_no"] == "KH-202608-0001"
        assert finalized.json()["status"] == "effective"

        word = client.get(f"/api/assessments/{draft['id']}/documents/word", headers=headers)
        pdf = client.get(f"/api/assessments/{draft['id']}/documents/pdf", headers=headers)
        assert word.status_code == 200 and word.content[:2] == b"PK"
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
        excel = client.get("/api/exports/assessment-ledger.xlsx", headers=headers)
        assert excel.status_code == 200 and excel.content[:2] == b"PK"

        copied = client.post(f"/api/assessments/{draft['id']}/copy", headers=headers)
        assert copied.status_code == 201
        assert copied.json()["status"] == "draft"
        assert copied.json()["assessment_no"] is None

        overview = client.get("/api/statistics/overview?today=2026-08-21", headers=headers)
        assert overview.status_code == 200
        assert overview.json()["month_count"] == 1
        assert overview.json()["month_amount"] == "0.50"


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
            "incident_date": "2026-08-22", "shift": "白班", "assessment_unit_id": second_unit["id"], "assessment_unit_name": second_unit["name"],
            "inspector_name": "部门主管", "assessment_content": "不应允许跨部门建单", "penalty_amount": "10.00",
        })
        assert forbidden.status_code == 403

        own_unit = manager_reference["units"][0]
        draft = client.post("/api/assessments", headers=manager_headers, json={
            "incident_date": "2026-08-22", "shift": "白班", "assessment_unit_id": own_unit["id"], "assessment_unit_name": own_unit["name"],
            "inspector_name": "部门主管", "assessment_content": "初始草稿", "penalty_amount": "10.00",
        }).json()
        updated = client.put(f"/api/assessments/{draft['id']}", headers=manager_headers, json={
            "incident_date": "2026-08-22", "shift": "夜班", "assessment_unit_id": own_unit["id"], "assessment_unit_name": own_unit["name"],
            "inspector_name": "部门主管", "assessment_content": "最后一次保存内容", "penalty_amount": "12.34", "updated_at": draft["updated_at"],
        })
        assert updated.status_code == 200
        formal = client.post(f"/api/assessments/{draft['id']}/finalize", headers=manager_headers).json()
        assert formal["assessment_content"] == "最后一次保存内容"
        assert formal["penalty_amount"] == "12.34"
        assert client.delete(f"/api/assessments/{draft['id']}", headers=admin).status_code == 405

        leader_token = client.post("/api/auth/login", json={"username": "leader", "password": "LeaderPassw0rd!"}).json()["access_token"]
        leader_headers = {"Authorization": f"Bearer {leader_token}"}
        assert client.get("/api/assessments", headers=leader_headers).status_code == 200
        assert client.post("/api/assessments", headers=leader_headers, json={}).status_code == 403
