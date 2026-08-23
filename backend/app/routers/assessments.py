from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..db import get_session
from ..deps import assert_record_scope, get_current_user, require_roles
from ..models import Assessment, User
from ..schemas import AssessmentInput, AssessmentOut, AssessmentPage, AssessmentUpdate, VoidRequest
from ..services import finalize_assessment, snapshot_for_input, utc_now

router = APIRouter(prefix="/api/assessments", tags=["考核单"])


def comparable_timestamp(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0)


def scoped_query(user: User) -> Select[tuple[Assessment]]:
    query = select(Assessment)
    if user.role == "department_manager":
        query = query.where(Assessment.department_id == user.department_id)
    return query


@router.post("", response_model=AssessmentOut, status_code=status.HTTP_201_CREATED)
def create_assessment(payload: AssessmentInput, session: Session = Depends(get_session), user: User = Depends(require_roles("admin", "department_manager"))) -> Assessment:
    values = snapshot_for_input(session, payload, user)
    assessment = Assessment(**values, created_by=user.id, status="draft")
    session.add(assessment)
    session.flush()
    write_audit_log(session, operator_id=user.id, action="assessment.create_draft", target_type="assessment", target_id=str(assessment.id), after={"status": "draft"})
    session.commit()
    return assessment


@router.get("", response_model=AssessmentPage)
def list_assessments(
    session: Session = Depends(get_session), user: User = Depends(get_current_user), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None, start_date: date | None = None, end_date: date | None = None, unit_id: int | None = None,
    shift: str | None = None, category_id: int | None = None, operation_stage: str | None = None, record_status: str | None = Query(None, alias="status"),
) -> AssessmentPage:
    filters = []
    if keyword:
        term = f"%{keyword.strip()}%"
        filters.append(or_(Assessment.assessment_no.ilike(term), Assessment.assessment_unit_name_snapshot.ilike(term), Assessment.inspector_name.ilike(term), Assessment.assessment_content.ilike(term)))
    if start_date: filters.append(Assessment.incident_date >= start_date)
    if end_date: filters.append(Assessment.incident_date <= end_date)
    if unit_id: filters.append(Assessment.assessment_unit_id == unit_id)
    if shift: filters.append(Assessment.shift == shift)
    if category_id: filters.append(Assessment.category_id == category_id)
    if operation_stage: filters.append(Assessment.operation_stage == operation_stage)
    if record_status: filters.append(Assessment.status == record_status)
    query = scoped_query(user).where(*filters).order_by(Assessment.incident_date.desc(), Assessment.id.desc())
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.execute(query.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return AssessmentPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{assessment_id}", response_model=AssessmentOut)
def get_assessment(assessment_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> Assessment:
    assessment = session.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核单不存在")
    assert_record_scope(user, assessment.department_id)
    return assessment


@router.put("/{assessment_id}", response_model=AssessmentOut)
def update_assessment(assessment_id: int, payload: AssessmentUpdate, session: Session = Depends(get_session), user: User = Depends(require_roles("admin", "department_manager"))) -> Assessment:
    assessment = session.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核单不存在")
    assert_record_scope(user, assessment.department_id)
    if assessment.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="正式考核单不可直接修改，请作废后重新开具")
    if comparable_timestamp(assessment.updated_at) != comparable_timestamp(payload.updated_at):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="记录已被其他用户更新，请刷新后再试")
    before = {"penalty_amount": str(assessment.penalty_amount), "assessment_content": assessment.assessment_content}
    for key, value in snapshot_for_input(session, payload, user).items():
        setattr(assessment, key, value)
    session.flush()
    write_audit_log(session, operator_id=user.id, action="assessment.update_draft", target_type="assessment", target_id=str(assessment.id), before=before, after={"penalty_amount": str(assessment.penalty_amount), "assessment_content": assessment.assessment_content})
    session.commit()
    return assessment


@router.post("/{assessment_id}/finalize", response_model=AssessmentOut)
def finalize(assessment_id: int, session: Session = Depends(get_session), user: User = Depends(require_roles("admin", "department_manager"))) -> Assessment:
    assessment = session.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核单不存在")
    assert_record_scope(user, assessment.department_id)
    try:
        assessment = finalize_assessment(session, assessment)
        write_audit_log(session, operator_id=user.id, action="assessment.finalize", target_type="assessment", target_id=str(assessment.id), after={"assessment_no": assessment.assessment_no, "status": "effective"})
        session.commit()
        return assessment
    except Exception:
        session.rollback()
        raise


@router.post("/{assessment_id}/copy", response_model=AssessmentOut, status_code=status.HTTP_201_CREATED)
def copy_assessment(assessment_id: int, session: Session = Depends(get_session), user: User = Depends(require_roles("admin", "department_manager"))) -> Assessment:
    original = session.get(Assessment, assessment_id)
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核单不存在")
    assert_record_scope(user, original.department_id)
    values = {column.name: getattr(original, column.name) for column in Assessment.__table__.columns if column.name not in {"id", "assessment_no", "status", "created_by", "created_at", "updated_at", "finalized_at", "voided_at", "voided_by", "void_reason"}}
    copied = Assessment(**values, assessment_no=None, status="draft", created_by=user.id)
    session.add(copied)
    session.flush()
    write_audit_log(session, operator_id=user.id, action="assessment.copy", target_type="assessment", target_id=str(copied.id), after={"source_id": original.id, "status": "draft"})
    session.commit()
    return copied


@router.post("/{assessment_id}/void", response_model=AssessmentOut)
def void_assessment(assessment_id: int, payload: VoidRequest, session: Session = Depends(get_session), user: User = Depends(require_roles("admin"))) -> Assessment:
    assessment = session.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核单不存在")
    if assessment.status != "effective":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有正式考核单可以作废")
    assessment.status = "voided"
    assessment.voided_at = utc_now()
    assessment.voided_by = user.id
    assessment.void_reason = payload.reason.strip()
    write_audit_log(session, operator_id=user.id, action="assessment.void", target_type="assessment", target_id=str(assessment.id), before={"status": "effective"}, after={"status": "voided", "reason": assessment.void_reason})
    session.commit()
    return assessment
