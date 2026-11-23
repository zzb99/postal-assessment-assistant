from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..db import get_session
from ..deps import assert_record_scope, get_current_user
from ..documents import DocumentGenerationError, read_archived_file
from ..models import Assessment, AssessmentDocument, User

router = APIRouter(prefix="/api/assessments", tags=["正式文书"])


def get_archive(assessment_id: int, session: Session, user: User) -> tuple[Assessment, AssessmentDocument]:
    assessment = session.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核单不存在")
    assert_record_scope(user, assessment.department_id, assessment.created_by)
    if assessment.status not in {"effective", "voided"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="草稿没有正式归档文书")
    if not assessment.document:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该记录缺少正式文书归档，禁止临时重建")
    return assessment, assessment.document


def archived_response(content: bytes, media_type: str, filename: str, disposition: str) -> Response:
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{assessment_id}/documents/word")
def export_word(assessment_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> Response:
    assessment, document = get_archive(assessment_id, session, user)
    try:
        content = read_archived_file(document.docx_path, document.docx_sha256)
    except DocumentGenerationError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    write_audit_log(session, operator_id=user.id, action="assessment.export_word", target_type="assessment", target_id=str(assessment.id), after={"assessment_no": assessment.assessment_no, "sha256": document.docx_sha256})
    session.commit()
    return archived_response(content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"{assessment.assessment_no}.docx", "attachment")


@router.get("/{assessment_id}/documents/pdf")
def export_pdf(assessment_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> Response:
    assessment, document = get_archive(assessment_id, session, user)
    try:
        content = read_archived_file(document.pdf_path, document.pdf_sha256)
    except DocumentGenerationError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    write_audit_log(session, operator_id=user.id, action="assessment.preview_pdf", target_type="assessment", target_id=str(assessment.id), after={"assessment_no": assessment.assessment_no, "sha256": document.pdf_sha256})
    session.commit()
    return archived_response(content, "application/pdf", f"{assessment.assessment_no}.pdf", "inline")
