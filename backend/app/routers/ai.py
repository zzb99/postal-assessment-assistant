from fastapi import APIRouter, Depends, HTTPException, status

from ..ai import AiServiceError, analyse_assessment, answer_policy
from ..deps import get_current_user, require_roles
from ..models import User
from ..schemas import AiAssessmentRequest, AiAssessmentResult, AiPolicyRequest, AiPolicyResult

router = APIRouter(prefix="/api/ai", tags=["智能辅助"])


@router.post("/assessment", response_model=AiAssessmentResult)
def assessment_assist(payload: AiAssessmentRequest, _: User = Depends(require_roles("admin", "department_manager"))) -> dict:
    try:
        return analyse_assessment(payload)
    except AiServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.post("/policy", response_model=AiPolicyResult)
def policy_assist(payload: AiPolicyRequest, _: User = Depends(get_current_user)) -> dict:
    try:
        return answer_policy(payload.question)
    except AiServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
