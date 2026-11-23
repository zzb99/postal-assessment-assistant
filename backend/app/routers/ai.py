from fastapi import APIRouter, Depends, HTTPException, status

from ..ai import AiServiceError, analyse_assessment, answer_policy
from .. import ai_usage
from ..config import settings
from ..deps import get_current_user, require_roles
from ..models import User
from ..schemas import AiAssessmentRequest, AiAssessmentResult, AiPolicyRequest, AiPolicyResult, AiUsageSummary

router = APIRouter(prefix="/api/ai", tags=["智能辅助"])


@router.get("/status")
def ai_status(_: User = Depends(get_current_user)) -> dict:
    return {"enabled": bool(settings.deepseek_api_key.strip()), "model": settings.deepseek_model, "max_tokens": settings.ai_max_tokens}


@router.post("/assessment", response_model=AiAssessmentResult)
def assessment_assist(payload: AiAssessmentRequest, _: User = Depends(require_roles("admin", "department_manager", "employee"))) -> dict:
    try:
        return analyse_assessment(payload, scope=f"user:{_.id}")
    except AiServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.post("/policy", response_model=AiPolicyResult)
def policy_assist(payload: AiPolicyRequest, _: User = Depends(get_current_user)) -> dict:
    try:
        return answer_policy(payload.question, scope=f"user:{_.id}")
    except AiServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.get("/usage", response_model=AiUsageSummary)
def usage_summary(_: User = Depends(require_roles("admin"))):
    return ai_usage.summary()
