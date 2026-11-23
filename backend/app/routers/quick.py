from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from .. import ai_writing
from ..ai import AiServiceError, rule_catalog
from ..config import settings
from ..db import get_session
from ..documents import DocumentGenerationError, cleanup_archive, read_archived_file
from ..models import Assessment, AssessmentCategory, AssessmentUnit, MasterDataItem, QuickSubmission
from ..quick import ai_limiter, device_hash, generation_slot, intake_actor, limit_submission, payload_hash
from ..schemas import AssessmentOut, AssessmentPage, QuickAssessmentInput, QuickConfig, QuickAiRequest, QuickAiResult, QuickAiContinueRequest
from ..services import finalize_assessment, snapshot_for_input
from .documents import archived_response
from .. import governance
from ..manual_amount import validate_manual_amount
from ..rule_search import get_index
from ..models import TrustedDevice
from ..schemas import QuickReconfirmRequest
from ..schemas import QuickAiSelectRequest

router = APIRouter(prefix="/api/quick", tags=["手机快捷填报"])


def owner_key(x_device_token: str | None = Header(default=None)) -> str:
    return device_hash(x_device_token)


@router.get("/device")
def device_status(response: Response, owner: str = Depends(owner_key), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "private, no-store"
    device = session.scalar(select(TrustedDevice).where(TrustedDevice.device_hash == owner))
    return governance.device_view(device) if device else {"status": "unregistered", "code": None}


@router.post("/device")
def register_device(payload: governance.DeviceIdentity, owner: str = Depends(owner_key), session: Session = Depends(get_session)):
    return governance.register_device(session, owner, payload)


@router.get("/config", response_model=QuickConfig)
def config(response: Response, session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    return {
        "units": [{"id": unit.id, "name": unit.name} for unit in session.scalars(select(AssessmentUnit).where(AssessmentUnit.active.is_(True)).order_by(AssessmentUnit.id))],
        "shifts": list(session.scalars(select(MasterDataItem.name).where(MasterDataItem.kind == "shift", MasterDataItem.active.is_(True)).order_by(MasterDataItem.sort_order))),
        "ai_enabled": bool(settings.deepseek_api_key.strip()),
        "regulation_version": str(get_index(datetime.now(ZoneInfo('Asia/Shanghai')).date()).catalog.get("version", "")),
    }


@router.post("/ai/compose", response_model=QuickAiResult)
def compose_notice(payload: QuickAiRequest, request: Request, response: Response, owner: str = Depends(owner_key), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "private, no-store"
    ai_limiter.check("device:" + owner, 12)
    ai_limiter.check("peer:" + (request.client.host if request.client else "unknown"), 60)
    ai_limiter.check("global", 60)
    if not settings.deepseek_api_key.strip():
        raise HTTPException(status_code=503, detail="服务端尚未配置DeepSeek密钥，问题描述已保留，可暂时手动填写")
    unit = session.get(AssessmentUnit, payload.assessment_unit_id)
    shift = session.scalar(select(MasterDataItem.id).where(MasterDataItem.kind == "shift", MasterDataItem.name == payload.shift, MasterDataItem.active.is_(True)))
    if unit is None or not unit.active or shift is None:
        raise HTTPException(status_code=422, detail="请选择有效的单位和班次")
    try:
        result = ai_writing.compose(SimpleNamespace(facts=payload.facts, incident_date=payload.incident_date, shift=payload.shift, assessment_unit_name=unit.name, assessment_unit_id=unit.id), scope="device:" + owner)
        if result["ready"]:
            result["proposal_token"] = ai_writing.sign_proposal(result, payload, owner)
        return result
    except AiServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/ai/continue", response_model=QuickAiResult)
def continue_notice(payload: QuickAiContinueRequest, request: Request, response: Response, owner: str = Depends(owner_key), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "private, no-store"
    ai_limiter.check("continue:" + owner, 60)
    try:
        result = ai_writing.recheck(payload.continuation_token, payload.answers, scope="device:" + owner)
        context = result.pop("_context")
        unit = session.get(AssessmentUnit, context["unit_id"])
        shift = session.scalar(select(MasterDataItem.id).where(MasterDataItem.kind == "shift", MasterDataItem.name == context["shift"], MasterDataItem.active.is_(True)))
        if unit is None or not unit.active or unit.name != context["unit"] or shift is None:
            raise HTTPException(status_code=422, detail="单位或班次已改变，请重新整理")
        if result["ready"]:
            form = SimpleNamespace(incident_date=context["date"], shift=context["shift"], assessment_unit_id=unit.id)
            result["proposal_token"] = ai_writing.sign_proposal(result, form, owner)
        return result
    except AiServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post('/ai/select', response_model=QuickAiResult)
def select_notice(payload: QuickAiSelectRequest, response: Response, owner: str = Depends(owner_key), session: Session = Depends(get_session)):
    response.headers['Cache-Control'] = 'private, no-store'
    ai_limiter.check('continue:' + owner, 60)
    try:
        result = ai_writing.select_candidate(payload.continuation_token, payload.rule_id, payload.pricing_id, scope='device:' + owner)
        context = result.pop('_context')
        unit = session.get(AssessmentUnit, context['unit_id'])
        shift = session.scalar(select(MasterDataItem.id).where(MasterDataItem.kind == 'shift', MasterDataItem.name == context['shift'], MasterDataItem.active.is_(True)))
        if unit is None or not unit.active or unit.name != context['unit'] or shift is None:
            raise HTTPException(422, '单位或班次已改变，请重新整理')
        if result['ready']:
            form = SimpleNamespace(incident_date=context['date'], shift=context['shift'], assessment_unit_id=unit.id)
            result['proposal_token'] = ai_writing.sign_proposal(result, form, owner)
        return result
    except AiServiceError as error:
        raise HTTPException(503, str(error)) from error


def find_submission(session, owner, request_id):
    return session.scalar(select(QuickSubmission).where(QuickSubmission.device_hash == owner, QuickSubmission.request_id == request_id))


@router.post('/ai/reconfirm')
def reconfirm_notice(payload: QuickReconfirmRequest, response: Response, owner: str = Depends(owner_key)):
    response.headers['Cache-Control'] = 'private, no-store'
    ai_limiter.check('reconfirm:' + owner, 60)
    if not payload.facts_confirmed: raise HTTPException(422, '请先核对并确认修改后的事实')
    return {'proposal_token': ai_writing.reconfirm(payload.original, payload.edited_content, owner)}


@router.post("/assessments", response_model=AssessmentOut)
def generate(payload: QuickAssessmentInput, request: Request, response: Response, owner: str = Depends(owner_key), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    limit_submission(request, owner)
    if not payload.ai_proposal:
        validate_manual_amount(payload.assessment_content, payload.penalty_amount)
    fingerprint = payload_hash(payload)
    submission = find_submission(session, owner, str(payload.request_id))
    if submission is None:
        proposal = ai_writing.verify_proposal(payload, owner) if payload.ai_proposal else None
        if proposal is None:
            validate_manual_amount(payload.assessment_content, payload.penalty_amount)
        governance.require_policy(session, proposal['version'] if proposal else str(get_index(payload.incident_date).catalog['version']), payload.incident_date, approval_required=False)
        actor = intake_actor(session)
        # Categorize only on an explicit unique category-name match; ambiguous facts stay 其他.
        categories = list(session.scalars(select(AssessmentCategory).where(AssessmentCategory.active.is_(True))))
        matches = [item for item in categories if item.name != "其他" and item.name in payload.assessment_content]
        category = matches[0] if len(matches) == 1 else next((item for item in categories if item.name == "其他"), None)
        clean = payload.model_copy(update={"category_id": category.id if category else None,
                                           "regulation_version": proposal["version"] if proposal else str(get_index(payload.incident_date).catalog.get("version", "")),
                                           "operation_stage": proposal["stage"] if proposal else None})
        values = snapshot_for_input(session, clean, actor)
        assessment = Assessment(**values, created_by=actor.id, status="draft")
        session.add(assessment); session.flush()
        submission = QuickSubmission(assessment_id=assessment.id, device_hash=owner, request_id=str(payload.request_id), request_sha256=fingerprint, ai_catalog_digest=proposal["catalog_digest"] if proposal else None)
        session.add(submission)
        write_audit_log(session, operator_id=actor.id, action="assessment.quick_draft", target_type="assessment", target_id=str(assessment.id), after={"team": assessment.team, "inspector_name": assessment.inspector_name})
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            submission = find_submission(session, owner, str(payload.request_id))
            if submission is None:
                raise
    if submission.request_sha256 != fingerprint:
        raise HTTPException(status_code=409, detail="本次提交内容已变化，请点击新建后重新生成")
    # Do not keep a connection/read transaction while waiting on document work.
    # The committed draft survives rollback; all authorization is checked again below.
    session.rollback()
    # Bound expensive anonymous work; never let a request queue grow without limit.
    if not generation_slot.acquire(timeout=45):
        raise HTTPException(status_code=429, detail="文书队列已满或等待超过45秒，草稿已保留，可用原提交安全重试", headers={"Retry-After": "5"})
    archived = None
    try:
        assessment = session.scalar(select(Assessment).where(Assessment.id == submission.assessment_id).with_for_update().execution_options(populate_existing=True))
        if assessment.status == "draft":
            if submission.ai_catalog_digest:
                if not payload.ai_proposal:
                    raise HTTPException(422, "AI草稿必须带有效的确认凭证，不能转成手工重试")
                ai_writing.verify_proposal(payload, owner)
            assessment, archived = finalize_assessment(session, assessment, public_intake=True)
            write_audit_log(session, operator_id=assessment.created_by, action="assessment.quick_finalize", target_type="assessment", target_id=str(assessment.id), after={"assessment_no": assessment.assessment_no})
            session.commit()
        return assessment
    except DocumentGenerationError as error:
        session.rollback(); cleanup_archive(archived.archive_dir if archived else None)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception:
        session.rollback(); cleanup_archive(archived.archive_dir if archived else None)
        raise
    finally:
        generation_slot.release()


@router.get("/assessments", response_model=AssessmentPage)
def recent(response: Response, page: int = Query(1, ge=1), owner: str = Depends(owner_key), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "private, no-store"
    query = select(Assessment).join(QuickSubmission, Assessment.id == QuickSubmission.assessment_id).where(QuickSubmission.device_hash == owner)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(session.scalars(query.order_by(Assessment.id.desc()).offset((page - 1) * 10).limit(10)))
    return AssessmentPage(items=items, total=total, page=page, page_size=10)


@router.get("/assessments/{assessment_id}/documents/{kind}")
def document(assessment_id: int, kind: str, owner: str = Depends(owner_key), session: Session = Depends(get_session)):
    assessment = session.scalar(select(Assessment).join(QuickSubmission, Assessment.id == QuickSubmission.assessment_id).where(Assessment.id == assessment_id, QuickSubmission.device_hash == owner))
    if assessment is None or kind not in {"word", "pdf"}:
        raise HTTPException(status_code=404, detail="本机找不到该文书")
    if assessment.status != "effective" or assessment.document is None:
        raise HTTPException(status_code=409, detail="该文书未正式生成或已作废，不能分享")
    archive = assessment.document
    try:
        data = read_archived_file(archive.docx_path if kind == "word" else archive.pdf_path, archive.docx_sha256 if kind == "word" else archive.pdf_sha256)
    except DocumentGenerationError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    media = "application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return archived_response(data, media, f"{assessment.assessment_no}.{'pdf' if kind == 'pdf' else 'docx'}", "attachment")
