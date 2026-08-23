from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..db import get_session
from ..deps import get_current_user, require_roles
from ..models import AssessmentCategory, AssessmentUnit, Department, MasterDataItem, User
from ..schemas import ActiveUpdate, ManagedUserOut, NamedItemCreate, UserCreate, UserUpdate
from ..security import hash_password

router = APIRouter(prefix="/api/management", tags=["系统管理"])


def _commit_unique(session: Session, detail: str) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from error


def _flush_unique(session: Session, detail: str) -> None:
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from error


@router.get("/reference-data")
def reference_data(session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> dict:
    department_filter = []
    unit_filter = []
    if user.role == "department_manager":
        department_filter.append(Department.id == user.department_id)
        unit_filter.append(AssessmentUnit.department_id == user.department_id)
    return {
        "departments": [{"id": item.id, "name": item.name, "active": item.active} for item in session.execute(select(Department).where(Department.active.is_(True), *department_filter).order_by(Department.name)).scalars()],
        "units": [{"id": item.id, "name": item.name, "department_id": item.department_id, "active": item.active} for item in session.execute(select(AssessmentUnit).where(AssessmentUnit.active.is_(True), *unit_filter).order_by(AssessmentUnit.name)).scalars()],
        "categories": [{"id": item.id, "name": item.name, "active": item.active} for item in session.execute(select(AssessmentCategory).where(AssessmentCategory.active.is_(True)).order_by(AssessmentCategory.name)).scalars()],
        "shifts": [item.name for item in session.execute(select(MasterDataItem).where(MasterDataItem.kind == "shift", MasterDataItem.active.is_(True)).order_by(MasterDataItem.sort_order, MasterDataItem.id)).scalars()],
        "operation_stages": [item.name for item in session.execute(select(MasterDataItem).where(MasterDataItem.kind == "operation_stage", MasterDataItem.active.is_(True)).order_by(MasterDataItem.sort_order, MasterDataItem.id)).scalars()],
    }


@router.get("/catalog")
def catalog(session: Session = Depends(get_session), _: User = Depends(require_roles("admin"))) -> dict:
    return {
        "departments": [{"id": x.id, "name": x.name, "active": x.active} for x in session.execute(select(Department).order_by(Department.id)).scalars()],
        "units": [{"id": x.id, "name": x.name, "department_id": x.department_id, "active": x.active} for x in session.execute(select(AssessmentUnit).order_by(AssessmentUnit.id)).scalars()],
        "categories": [{"id": x.id, "name": x.name, "active": x.active} for x in session.execute(select(AssessmentCategory).order_by(AssessmentCategory.id)).scalars()],
        "master_items": [{"id": x.id, "kind": x.kind, "name": x.name, "active": x.active, "sort_order": x.sort_order} for x in session.execute(select(MasterDataItem).order_by(MasterDataItem.kind, MasterDataItem.sort_order, MasterDataItem.id)).scalars()],
    }


@router.get("/users", response_model=list[ManagedUserOut])
def list_users(session: Session = Depends(get_session), _: User = Depends(require_roles("admin"))) -> list[User]:
    return list(session.execute(select(User).order_by(User.id)).scalars())


@router.post("/users", response_model=ManagedUserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: Session = Depends(get_session), admin: User = Depends(require_roles("admin"))) -> User:
    if payload.role == "department_manager" and payload.department_id is None:
        raise HTTPException(status_code=422, detail="部门主管必须绑定部门")
    if payload.department_id and not session.get(Department, payload.department_id):
        raise HTTPException(status_code=422, detail="部门不存在")
    item = User(username=payload.username.strip(), display_name=payload.display_name.strip(), password_hash=hash_password(payload.password), role=payload.role, department_id=payload.department_id, active=True)
    session.add(item); _flush_unique(session, "用户名已存在")
    write_audit_log(session, operator_id=admin.id, action="user.create", target_type="user", target_id=str(item.id), after={"username": item.username, "role": item.role, "department_id": item.department_id})
    _commit_unique(session, "用户名已存在")
    return item


@router.put("/users/{user_id}", response_model=ManagedUserOut)
def update_user(user_id: int, payload: UserUpdate, session: Session = Depends(get_session), admin: User = Depends(require_roles("admin"))) -> User:
    item = session.get(User, user_id)
    if not item:
        raise HTTPException(status_code=404, detail="用户不存在")
    if item.id == admin.id and not payload.active:
        raise HTTPException(status_code=409, detail="不能停用当前登录账号")
    if payload.role == "department_manager" and payload.department_id is None:
        raise HTTPException(status_code=422, detail="部门主管必须绑定部门")
    if payload.department_id and not session.get(Department, payload.department_id):
        raise HTTPException(status_code=422, detail="部门不存在")
    before = {"display_name": item.display_name, "role": item.role, "department_id": item.department_id, "active": item.active}
    item.display_name = payload.display_name.strip(); item.role = payload.role; item.department_id = payload.department_id; item.active = payload.active
    if payload.password:
        item.password_hash = hash_password(payload.password)
    write_audit_log(session, operator_id=admin.id, action="user.update", target_type="user", target_id=str(item.id), before=before, after={"display_name": item.display_name, "role": item.role, "department_id": item.department_id, "active": item.active, "password_reset": bool(payload.password)})
    session.commit()
    return item


@router.post("/{kind}", status_code=status.HTTP_201_CREATED)
def create_catalog_item(kind: str, payload: NamedItemCreate, session: Session = Depends(get_session), admin: User = Depends(require_roles("admin"))) -> dict:
    if kind == "departments":
        item = Department(name=payload.name)
    elif kind == "units":
        if payload.department_id is None or not session.get(Department, payload.department_id):
            raise HTTPException(status_code=422, detail="被考核单位必须绑定有效部门")
        item = AssessmentUnit(name=payload.name, department_id=payload.department_id)
    elif kind == "categories":
        item = AssessmentCategory(name=payload.name)
    elif kind in {"shifts", "operation-stages"}:
        master_kind = "shift" if kind == "shifts" else "operation_stage"
        max_sort = session.scalar(select(func.max(MasterDataItem.sort_order)).where(MasterDataItem.kind == master_kind)) or 0
        item = MasterDataItem(kind=master_kind, name=payload.name, sort_order=max_sort + 1)
    else:
        raise HTTPException(status_code=404, detail="基础数据类型不存在")
    session.add(item); _flush_unique(session, "名称已存在")
    write_audit_log(session, operator_id=admin.id, action="catalog.create", target_type=kind, target_id=str(item.id), after={"name": payload.name, "department_id": payload.department_id})
    _commit_unique(session, "名称已存在")
    return {"id": item.id, "name": item.name, "active": item.active}


@router.put("/{kind}/{item_id}/active")
def set_catalog_active(kind: str, item_id: int, payload: ActiveUpdate, session: Session = Depends(get_session), admin: User = Depends(require_roles("admin"))) -> dict:
    model = {"departments": Department, "units": AssessmentUnit, "categories": AssessmentCategory, "shifts": MasterDataItem, "operation-stages": MasterDataItem}.get(kind)
    if model is None:
        raise HTTPException(status_code=404, detail="基础数据类型不存在")
    item = session.get(model, item_id)
    expected_kind = "shift" if kind == "shifts" else "operation_stage"
    if not item or (isinstance(item, MasterDataItem) and item.kind != expected_kind):
        raise HTTPException(status_code=404, detail="基础数据不存在")
    before = item.active; item.active = payload.active
    write_audit_log(session, operator_id=admin.id, action="catalog.set_active", target_type=kind, target_id=str(item.id), before={"active": before}, after={"active": item.active})
    session.commit()
    return {"id": item.id, "name": item.name, "active": item.active}
