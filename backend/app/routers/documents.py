from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..db import get_session
from ..deps import assert_record_scope, get_current_user
from ..documents import build_pdf, build_word
from ..models import Assessment, User

router = APIRouter(prefix="/api/assessments", tags=["正式文书"])


def get_effective(assessment_id: int, session: Session, user: User) -> Assessment:
    assessment = session.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核单不存在")
    assert_record_scope(user, assessment.department_id)
    if assessment.status != "effective":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有正式考核单可以导出正式文书")
    return assessment


@router.get("/{assessment_id}/documents/word")
def export_word(assessment_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> Response:
    assessment = get_effective(assessment_id, session, user)
    content = build_word(assessment)
    write_audit_log(session, operator_id=user.id, action="assessment.export_word", target_type="assessment", target_id=str(assessment.id), after={"assessment_no": assessment.assessment_no})
    session.commit()
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f"attachment; filename={assessment.assessment_no}.docx"})


@router.get("/{assessment_id}/documents/pdf")
def export_pdf(assessment_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> Response:
    assessment = get_effective(assessment_id, session, user)
    content = build_pdf(assessment)
    write_audit_log(session, operator_id=user.id, action="assessment.export_pdf", target_type="assessment", target_id=str(assessment.id), after={"assessment_no": assessment.assessment_no})
    session.commit()
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={assessment.assessment_no}.pdf"})
