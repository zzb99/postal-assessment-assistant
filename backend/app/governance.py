"""One-time device capability approval and exact-catalog policy approval.

Approval is a human business decision, never inferred from historical samples.
"""
import hashlib
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .audit import write_audit_log
from .config import settings
from .db import SessionLocal, get_session
from .deps import require_roles
from .models import PolicyApproval, TrustedDevice, User
from .quick import ai_limiter, device_hash
from .rule_search import get_index
from .policy_store import select_entry
from .people import normalize_team, normalize_person

router = APIRouter(prefix="/api/governance", tags=["授权与制度核准"])


class DeviceIdentity(BaseModel):
    team: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)


class ApprovalInput(BaseModel):
    approved: StrictBool
    code: str = Field(min_length=8, max_length=16)


class PolicyInput(BaseModel):
    digest: str = Field(min_length=1, max_length=64)


def device_view(device):
    return {"id": device.id, "code": device.code, "team": device.team, "name": device.name, "status": device.status}


def register_device(session, owner, identity):
    ai_limiter.check("registration-global", 200)
    team, name = normalize_team(identity.team), normalize_person(identity.name)
    if not team or not name:
        raise HTTPException(422, "班组和姓名不能为空")
    device = session.scalar(select(TrustedDevice).where(TrustedDevice.device_hash == owner).with_for_update())
    if device is None:
        if (session.scalar(select(func.count()).select_from(TrustedDevice)) or 0) >= 5000:
            raise HTTPException(429, "设备登记已达容量，请管理员处理")
        device = TrustedDevice(device_hash=owner, code=secrets.token_hex(4).upper(), team=team, name=name, status="pending")
        session.add(device)
    elif (device.team, device.name) != (team, name):
        device.team, device.name = team, name
        device.code = secrets.token_hex(4).upper()  # Invalidate a manager's stale identity approval.
        if device.status != "revoked": device.status = "pending"
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, "设备登记发生冲突，请重试") from error
    return device_view(device)


def policy_status(session):
    index = get_index()
    current = select_entry()
    approved = session.get(PolicyApproval, index.digest)
    return {"version": index.catalog["version"], "effective_date": current['effective_date'] if current else '2026-08-19',
            "digest": index.digest, "source": index.catalog["source"],
            "approval_status": 'published' if current else ('approved' if approved else 'legacy'),
            "approved_at": current['published_at'] if current else (approved.approved_at.isoformat() if approved else None),
            "notice": '主管或管理员可上传新Word直接发布；复杂金额条款需要据原文人工核定。'}


def require_formal_authority(session, owner, version, incident_date, *, identity=None):
    if settings.require_trusted_device:
        device = session.scalar(select(TrustedDevice).where(TrustedDevice.device_hash == owner))
        if device is None or device.status != "approved":
            raise HTTPException(403, "本设备尚未授权正式出单，请登记一次并联系主管核准；输入内容仍保留")
        if identity and (device.team, device.name) != identity:
            raise HTTPException(403, "班组或姓名已改变，请重新登记授权")
    require_policy(session, version, incident_date)


def require_policy(session, version, incident_date, *, approval_required=None):
    from .policy_store import select_entry
    when = date.fromisoformat(str(incident_date))
    index = get_index(when)
    chosen = select_entry(when)
    effective = date.fromisoformat(chosen['effective_date'] if chosen else '2026-08-19')
    if str(version) != str(index.catalog['version']) or when < effective:
        raise HTTPException(409, '检查日期与适用制度版本不符，请刷新并核对')
    # Publishing is authorized by manager/admin upload; no additional approval gate.


@router.get("/devices")
def devices(response: Response, _: User = Depends(require_roles("admin")), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "private, no-store"
    return [device_view(d) for d in session.scalars(select(TrustedDevice).order_by(TrustedDevice.id.desc()).limit(5000))]


@router.put("/devices/{device_id}")
def approve_device(device_id: int, payload: ApprovalInput, user: User = Depends(require_roles("admin")), session: Session = Depends(get_session)):
    device = session.scalar(select(TrustedDevice).where(TrustedDevice.id == device_id).with_for_update())
    if device is None: raise HTTPException(404, "设备不存在")
    if device.code != payload.code: raise HTTPException(409, "设备身份已变化，请刷新后重新核对")
    device.status = "approved" if payload.approved else "revoked"
    device.approved_by = user.id
    write_audit_log(session, operator_id=user.id, action="device." + device.status, target_type="device", target_id=str(device.id), after={"code": device.code})
    session.commit()
    return device_view(device)


@router.get("/policy")
def policy(response: Response, _: User = Depends(require_roles("admin", "department_manager")), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "private, no-store"
    return policy_status(session)


@router.post("/policy/approve")
def approve_policy(payload: PolicyInput, user: User = Depends(require_roles("admin")), session: Session = Depends(get_session)):
    index = get_index()
    if payload.digest != index.digest: raise HTTPException(409, "目录摘要已变化，请刷新后重新核对")
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if session.get_bind().dialect.name == 'postgresql' else sqlite_insert
    statement = insert(PolicyApproval).values(digest=index.digest, version=index.catalog['version'], approved_by=user.id).on_conflict_do_nothing(index_elements=[PolicyApproval.digest]).returning(PolicyApproval.digest)
    if session.scalar(statement):
        write_audit_log(session, operator_id=user.id, action="policy.approve", target_type="policy", target_id=index.digest, after={"version": index.catalog["version"]})
    session.commit()
    return policy_status(session)


@router.get("/rules")
def rules(response: Response, _: User = Depends(require_roles("admin", "department_manager", "leader"))):
    response.headers["Cache-Control"] = "private, no-store"
    return get_index().catalog
