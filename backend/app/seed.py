from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AssessmentCategory, AssessmentUnit, Department, MasterDataItem


def _ensure(session: Session, model, **values):
    existing = session.execute(select(model).filter_by(**values)).scalar_one_or_none()
    if not existing:
        session.add(model(**values))


def seed_reference_data(session: Session) -> None:
    for index, name in enumerate(("白班", "夜班")):
        _ensure(session, MasterDataItem, kind="shift", name=name, sort_order=index)
    for index, name in enumerate(("一班", "二班", "三班")):
        _ensure(session, MasterDataItem, kind="team", name=name, sort_order=index)
    for index, (team, name) in enumerate((("一班", "吴正一"), ("二班", "黄旭东"), ("三班", "魏振"))):
        _ensure(session, MasterDataItem, kind="inspector", name=name, parent_name=team, sort_order=index)
    for index, name in enumerate(("卸车", "矩阵", "小件机", "异形", "装车", "问题件处理", "安全生产", "其他")):
        _ensure(session, MasterDataItem, kind="operation_stage", name=name, sort_order=index)
    for name in ("白送", "错发", "邮件滞留", "现场管理", "安全生产", "操作不规范", "其他"):
        _ensure(session, AssessmentCategory, name=name)
    department = session.execute(select(Department).where(Department.name == "邮件处理中心")).scalar_one_or_none()
    if not department:
        department = Department(name="邮件处理中心")
        session.add(department)
        session.flush()
    for name in ("华阳公司", "君盈公司"):
        unit = session.execute(select(AssessmentUnit).where(AssessmentUnit.name == name)).scalar_one_or_none()
        if not unit:
            session.add(AssessmentUnit(name=name, department_id=department.id))


def run() -> None:
    from .db import SessionLocal
    with SessionLocal.begin() as session:
        seed_reference_data(session)


if __name__ == "__main__":
    run()
