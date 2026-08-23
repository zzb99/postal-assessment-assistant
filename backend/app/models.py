from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    department: Mapped[Department | None] = relationship()


class AssessmentUnit(Base):
    __tablename__ = "assessment_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    department: Mapped[Department | None] = relationship()


class AssessmentCategory(Base):
    __tablename__ = "assessment_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MasterDataItem(Base):
    __tablename__ = "master_data_items"
    __table_args__ = (UniqueConstraint("kind", "name", name="uq_master_data_kind_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class NumberSequence(Base):
    __tablename__ = "assessment_number_sequences"

    period: Mapped[str] = mapped_column(String(6), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_no: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)
    incident_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(32), index=True)
    assessment_unit_id: Mapped[int | None] = mapped_column(ForeignKey("assessment_units.id"), nullable=True, index=True)
    assessment_unit_name_snapshot: Mapped[str] = mapped_column(String(160))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    department_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    inspector_name: Mapped[str] = mapped_column(String(100), index=True)
    assessment_content: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("assessment_categories.id"), nullable=True, index=True)
    category_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operation_stage: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    regulation_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    penalty_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    penalty_amount_cn: Mapped[str] = mapped_column(String(100), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    unit: Mapped[AssessmentUnit | None] = relationship(foreign_keys=[assessment_unit_id])
    department: Mapped[Department | None] = relationship(foreign_keys=[department_id])
    category: Mapped[AssessmentCategory | None] = relationship()
    creator: Mapped[User] = relationship(foreign_keys=[created_by])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
