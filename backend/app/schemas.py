from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    assessment_unit_id: int | None = None
    assessment_unit_name: str = Field(min_length=1, max_length=160)
    inspector_name: str = Field(min_length=1, max_length=100)
    assessment_content: str = Field(min_length=1, max_length=8000)
    category_id: int | None = None
    operation_stage: str | None = Field(default=None, max_length=100)
    regulation_version: str | None = Field(default=None, max_length=64)
    penalty_amount: Decimal = Field(ge=Decimal("0"), max_digits=14, decimal_places=2)
    remark: str | None = Field(default=None, max_length=4000)

    @field_validator("assessment_unit_name", "inspector_name", "assessment_content")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class AssessmentUpdate(AssessmentInput):
    updated_at: datetime


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assessment_no: str | None
    incident_date: date
    shift: str
    assessment_unit_id: int | None
    assessment_unit_name_snapshot: str
    department_id: int | None
    department_name_snapshot: str | None
    inspector_name: str
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
        if value not in {"admin", "leader", "department_manager"}:
            raise ValueError("角色无效")
        return value


class UserUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    role: str
    department_id: int | None = None
    active: bool
    password: str | None = Field(default=None, min_length=10, max_length=256)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"admin", "leader", "department_manager"}:
            raise ValueError("角色无效")
        return value


class ManagedUserOut(UserOut):
    active: bool


class NamedItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    department_id: int | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("名称不能为空")
        return value


class ActiveUpdate(BaseModel):
    active: bool
