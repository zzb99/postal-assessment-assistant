from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .documents import ArchivedFiles, archive_documents, cleanup_archive
from .models import Assessment, AssessmentCategory, AssessmentDocument, AssessmentUnit, Department, MasterDataItem, NumberSequence, User
from .money import amount_to_chinese
from .schemas import AssessmentInput


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def snapshot_for_input(session: Session, payload: AssessmentInput, user: User) -> dict:
    unit = session.get(AssessmentUnit, payload.assessment_unit_id) if payload.assessment_unit_id else None
    if unit is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="请选择有效的被考核单位")
    if unit and not unit.active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="被考核单位已停用")
    if user.role == "department_manager" and unit and unit.department_id != user.department_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能选择本部门被考核单位")
    category = session.get(AssessmentCategory, payload.category_id) if payload.category_id else None
    if category and not category.active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="问题分类已停用")
    for kind, value, label in (("shift", payload.shift, "班次"), ("team", payload.team, "班组")):
        found = session.execute(select(MasterDataItem).where(MasterDataItem.kind == kind, MasterDataItem.name == value, MasterDataItem.active.is_(True))).scalar_one_or_none()
        if not found:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{label}无效或已停用")
    inspector = session.execute(
        select(MasterDataItem).where(
            MasterDataItem.kind == "inspector",
            MasterDataItem.name == payload.inspector_name,
            MasterDataItem.parent_name == payload.team,
            MasterDataItem.active.is_(True),
        )
    ).scalar_one_or_none()
    if not inspector:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="检查人不属于所选班组或已停用")
    department_id = user.department_id if user.role == "department_manager" else (unit.department_id if unit else user.department_id)
    department = session.get(Department, department_id) if department_id else None
    amount = Decimal(payload.penalty_amount).quantize(Decimal("0.01"))
    return {
        "incident_date": payload.incident_date,
        "shift": payload.shift,
        "team": payload.team,
        "assessment_unit_id": unit.id if unit else None,
        "assessment_unit_name_snapshot": unit.name if unit else payload.assessment_unit_name,
        "department_id": department.id if department else None,
        "department_name_snapshot": department.name if department else None,
        "inspector_name": payload.inspector_name,
        "quantity": payload.quantity,
        "assessment_content": payload.assessment_content,
        "category_id": category.id if category else None,
        "category_name_snapshot": category.name if category else None,
        "operation_stage": payload.operation_stage,
        "regulation_version": payload.regulation_version,
        "penalty_amount": amount,
        "penalty_amount_cn": amount_to_chinese(amount),
        "remark": payload.remark,
    }


def allocate_assessment_no(session: Session, incident_date) -> str:
    """Atomically increment a monthly sequence; never derive a number from count()."""
    period = incident_date.strftime("%Y%m")
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        # The supported production target is PostgreSQL; this keeps local/dev
        # databases safe when their dialect supports row locks.
        sequence = session.execute(
            select(NumberSequence).where(NumberSequence.period == period).with_for_update()
        ).scalar_one_or_none()
        if sequence is None:
            sequence = NumberSequence(period=period, last_number=1)
            session.add(sequence)
            session.flush()
            number = 1
        else:
            sequence.last_number += 1
            number = sequence.last_number
        return f"KH-{period}-{number:04d}"

    statement = (
        insert(NumberSequence)
        .values(period=period, last_number=1)
        .on_conflict_do_update(
            index_elements=[NumberSequence.period],
            set_={"last_number": NumberSequence.last_number + 1},
        )
        .returning(NumberSequence.last_number)
    )
    number = session.execute(statement).scalar_one()
    return f"KH-{period}-{number:04d}"


def finalize_assessment(session: Session, assessment: Assessment) -> tuple[Assessment, ArchivedFiles]:
    if assessment.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有草稿可以定稿")
    assessment.assessment_no = allocate_assessment_no(session, assessment.incident_date)
    generated_at = utc_now()
    archived: ArchivedFiles | None = None
    try:
        archived = archive_documents(assessment, generated_at)
        session.add(AssessmentDocument(
            assessment=assessment,
            template_version=settings.document_template_version,
            template_sha256=archived.template_sha256,
            docx_path=archived.docx_path,
            pdf_path=archived.pdf_path,
            docx_sha256=archived.docx_sha256,
            pdf_sha256=archived.pdf_sha256,
            generated_at=generated_at,
        ))
        assessment.status = "effective"
        assessment.finalized_at = generated_at
        session.flush()
        return assessment, archived
    except Exception:
        cleanup_archive(archived.archive_dir if archived else None)
        raise
