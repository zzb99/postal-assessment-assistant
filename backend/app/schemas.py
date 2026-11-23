from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from .people import normalize_person, normalize_team


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    role: str
    department_id: int | None


class AssessmentInput(BaseModel):
    incident_date: date
    shift: str = Field(min_length=1, max_length=32)
    team: str = Field(min_length=1, max_length=32)
    assessment_unit_id: int | None = None
    assessment_unit_name: str = Field(min_length=1, max_length=160)
    inspector_name: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=100000)
    assessment_content: str = Field(min_length=1, max_length=600)
    category_id: int | None = None
    operation_stage: str | None = Field(default=None, max_length=100)
    regulation_version: str | None = Field(default=None, max_length=64)
    penalty_amount: Decimal = Field(gt=Decimal("0"), le=Decimal("100000000"), multiple_of=Decimal("1"), max_digits=14, decimal_places=2)
    remark: str | None = Field(default=None, max_length=4000)

    @field_validator("team", mode="before")
    @classmethod
    def normalize_team_input(cls, value):
        return normalize_team(value) if isinstance(value, str) else value

    @field_validator("inspector_name", mode="before")
    @classmethod
    def normalize_inspector_input(cls, value):
        return normalize_person(value) if isinstance(value, str) else value

    @field_validator("shift", "team", "assessment_unit_name", "inspector_name", "assessment_content")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("assessment_content")
    @classmethod
    def limit_explicit_lines(cls, value: str) -> str:
        if value.count("\n") > 10:
            raise ValueError("考核事项最多允许10个换行")
        return value


class AssessmentUpdate(AssessmentInput):
    updated_at: datetime


class QuickAssessmentInput(AssessmentInput):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    ai_proposal: str | None = Field(default=None, max_length=10000)


class QuickUnit(BaseModel):
    id: int
    name: str


class QuickReconfirmRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    original: QuickAssessmentInput
    edited_content: str = Field(min_length=2, max_length=600)
    facts_confirmed: StrictBool


class QuickConfig(BaseModel):
    units: list[QuickUnit]
    shifts: list[str]
    ai_enabled: bool
    regulation_version: str


class QuickAiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: str = Field(min_length=2, max_length=1000)
    incident_date: date
    shift: str = Field(min_length=1, max_length=32)
    assessment_unit_id: int = Field(gt=0)

    @field_validator("facts", "shift")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("请填写具体问题")
        return value


class QuickAiContinueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    continuation_token: str = Field(min_length=10, max_length=5000)
    answers: dict[str, StrictBool | StrictInt] = Field(min_length=1, max_length=4)


class QuickAiSelectRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    continuation_token: str = Field(min_length=10, max_length=5000)
    rule_id: str = Field(min_length=1, max_length=80)
    pricing_id: str = Field(min_length=1, max_length=80)


class AiConditionQuestion(BaseModel):
    id: str
    question: str
    kind: str


class AiCandidateRule(BaseModel):
    id: str
    clause: str
    original: str
    pricing_options: list[dict] = Field(default_factory=list)


class QuickAiResult(BaseModel):
    ready: bool
    rule_id: str | None
    pricing_id: str | None
    quantity: int | None
    penalty_amount: Decimal | None
    assessment_content: str | None
    confidence: str
    reason: str
    clarifications: list[str]
    operation_stage: str | None
    regulation_version: str | None
    proposal_token: str | None = None
    draft_content: str | None = None
    clarification_choices: list[str] = Field(default_factory=list)
    continuation_token: str | None = None
    condition_questions: list[AiConditionQuestion] = Field(default_factory=list)
    candidate_rules: list[AiCandidateRule] = Field(default_factory=list)
    local_cache_hit: bool = False
    disposition: str = 'choose_rule'
    writing_notice: str | None = None


class AiUsageDay(BaseModel):
    date: str
    calls: int
    total_tokens: int
    estimated_cny: Decimal | None


class AiUsageSummary(BaseModel):
    today_prompt_tokens: int = 0
    today_cache_hit_tokens: int = 0
    today_cache_miss_tokens: int = 0
    today_output_tokens: int = 0
    provider_success_rate: float | None = None
    failure_reasons: dict[str, int] = Field(default_factory=dict)
    today_calls: int
    today_total_tokens: int
    today_estimated_cny: Decimal | None
    seven_day_estimated_cny: Decimal | None
    average_assessment_cny: Decimal | None
    local_cache_hit_rate: float
    mean_latency_ms: float
    p95_latency_ms: float
    unknown_usage_calls: int
    price_note: str
    days: list[AiUsageDay]


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assessment_no: str | None
    incident_date: date
    shift: str
    team: str
    assessment_unit_id: int | None
    assessment_unit_name_snapshot: str
    department_id: int | None
    department_name_snapshot: str | None
    inspector_name: str
    quantity: int
    assessment_content: str
    category_id: int | None
    category_name_snapshot: str | None
    operation_stage: str | None
    regulation_version: str | None
    penalty_amount: Decimal
    penalty_amount_cn: str
    remark: str | None
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None


class AssessmentPage(BaseModel):
    items: list[AssessmentOut]
    total: int
    page: int
    page_size: int


class VoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class OverviewStatistics(BaseModel):
    month_count: int
    month_amount: Decimal
    year_count: int
    year_amount: Decimal
    unit_count: int


class GroupStatistics(BaseModel):
    name: str
    count: int
    amount: Decimal


class MasterDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    active: bool


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=256)
    role: str
    department_id: int | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"admin", "leader", "department_manager", "employee"}:
            raise ValueError("角色无效")
        return value


class FinalizeRequest(BaseModel):
    updated_at: datetime


class UserUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    role: str
    department_id: int | None = None
    active: bool
    password: str | None = Field(default=None, min_length=10, max_length=256)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"admin", "leader", "department_manager", "employee"}:
            raise ValueError("角色无效")
        return value


class ManagedUserOut(UserOut):
    active: bool


class NamedItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    department_id: int | None = None
    parent_name: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("名称不能为空")
        return value


class ActiveUpdate(BaseModel):
    active: bool


class AiAssessmentRequest(BaseModel):
    facts: str = Field(min_length=2, max_length=2000)
    incident_date: date
    shift: str = Field(min_length=1, max_length=32)
    assessment_unit_name: str = Field(min_length=1, max_length=160)


class AiAssessmentResult(BaseModel):
    rule_id: str | None
    pricing_id: str | None
    quantity: int | None
    penalty_amount: Decimal | None
    assessment_content: str | None
    confidence: str
    reason: str
    needs_supervisor_review: bool


class AiPolicyRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class AiPolicyResult(BaseModel):
    rule_ids: list[str]
    conclusion: str
    recommended_action: str
    consequence: str
    needs_supervisor_review: bool
