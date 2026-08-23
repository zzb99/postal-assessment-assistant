from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..deps import get_current_user
from ..models import Assessment, User
from ..schemas import GroupStatistics, OverviewStatistics

router = APIRouter(prefix="/api/statistics", tags=["统计"])


def effective_scope(user: User, start_date: date | None = None, end_date: date | None = None):
    filters = [Assessment.status == "effective"]
    if user.role == "department_manager":
        filters.append(Assessment.department_id == user.department_id)
    if start_date:
        filters.append(Assessment.incident_date >= start_date)
    if end_date:
        filters.append(Assessment.incident_date <= end_date)
    return filters


@router.get("/overview", response_model=OverviewStatistics)
def overview(session: Session = Depends(get_session), user: User = Depends(get_current_user), today: date = Query(default_factory=date.today)) -> OverviewStatistics:
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    def aggregate(start: date):
        count, amount = session.execute(select(func.count(Assessment.id), func.coalesce(func.sum(Assessment.penalty_amount), 0)).where(*effective_scope(user, start, today))).one()
        return int(count or 0), Decimal(amount or 0)
    month_count, month_amount = aggregate(month_start)
    year_count, year_amount = aggregate(year_start)
    units = session.scalar(select(func.count(func.distinct(Assessment.assessment_unit_name_snapshot))).where(*effective_scope(user, month_start, today))) or 0
    return OverviewStatistics(month_count=month_count, month_amount=month_amount, year_count=year_count, year_amount=year_amount, unit_count=int(units))


def grouped(session: Session, user: User, field, start_date: date | None, end_date: date | None) -> list[GroupStatistics]:
    rows = session.execute(
        select(field, func.count(Assessment.id), func.coalesce(func.sum(Assessment.penalty_amount), 0))
        .where(*effective_scope(user, start_date, end_date))
        .group_by(field)
        .order_by(func.sum(Assessment.penalty_amount).desc(), func.count(Assessment.id).desc())
    ).all()
    return [GroupStatistics(name=name or "未分类", count=int(count), amount=Decimal(amount)) for name, count, amount in rows]


@router.get("/units", response_model=list[GroupStatistics])
def by_units(start_date: date | None = None, end_date: date | None = None, session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> list[GroupStatistics]:
    return grouped(session, user, Assessment.assessment_unit_name_snapshot, start_date, end_date)


@router.get("/departments", response_model=list[GroupStatistics])
def by_departments(start_date: date | None = None, end_date: date | None = None, session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> list[GroupStatistics]:
    return grouped(session, user, Assessment.department_name_snapshot, start_date, end_date)


@router.get("/categories", response_model=list[GroupStatistics])
def by_categories(start_date: date | None = None, end_date: date | None = None, session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> list[GroupStatistics]:
    return grouped(session, user, Assessment.category_name_snapshot, start_date, end_date)
