from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..db import get_session
from ..deps import get_current_user
from ..models import Assessment, User

router = APIRouter(prefix="/api/exports", tags=["Excel 导出"])


def visible_filters(user: User, *, keyword: str | None, record_status: str | None, start_date: date | None, end_date: date | None):
    filters = []
    if user.role == "department_manager": filters.append(Assessment.department_id == user.department_id)
    if keyword:
        term = f"%{keyword.strip()}%"
        filters.append(or_(Assessment.assessment_no.ilike(term), Assessment.assessment_unit_name_snapshot.ilike(term), Assessment.inspector_name.ilike(term), Assessment.assessment_content.ilike(term)))
    if record_status: filters.append(Assessment.status == record_status)
    if start_date: filters.append(Assessment.incident_date >= start_date)
    if end_date: filters.append(Assessment.incident_date <= end_date)
    return filters


def style_sheet(sheet) -> None:
    fill = PatternFill("solid", fgColor="1F568F")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


@router.get("/assessment-ledger.xlsx")
def export_ledger(
    keyword: str | None = None, record_status: str | None = Query(None, alias="status"), start_date: date | None = None, end_date: date | None = None,
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> Response:
    filters = visible_filters(user, keyword=keyword, record_status=record_status, start_date=start_date, end_date=end_date)
    records = session.execute(select(Assessment).where(*filters).order_by(Assessment.incident_date.desc(), Assessment.id.desc())).scalars().all()
    workbook = Workbook(); ledger = workbook.active; ledger.title = "考核台账"
    ledger.append(["考核编号", "发生日期", "班次", "被考核单位", "所属部门", "问题类型", "作业环节", "检查人", "处罚金额", "金额大写", "状态", "考核事项", "备注", "考核办法版本", "创建时间"])
    for item in records:
        ledger.append([item.assessment_no or "草稿", item.incident_date, item.shift, item.assessment_unit_name_snapshot, item.department_name_snapshot or "", item.category_name_snapshot or "", item.operation_stage or "", item.inspector_name, item.penalty_amount, item.penalty_amount_cn, item.status, item.assessment_content, item.remark or "", item.regulation_version or "", item.created_at.replace(tzinfo=None)])
    for row in ledger.iter_rows(min_row=2, min_col=9, max_col=9): row[0].number_format = '#,##0.00'
    for column, width in {"A": 20, "B": 13, "C": 10, "D": 18, "E": 16, "F": 14, "G": 14, "H": 13, "I": 14, "J": 18, "K": 12, "L": 54, "M": 32, "N": 16, "O": 20}.items(): ledger.column_dimensions[column].width = width
    style_sheet(ledger)
    effective = [item for item in records if item.status == "effective"]
    for title, key in (("单位汇总", lambda item: item.assessment_unit_name_snapshot), ("部门汇总", lambda item: item.department_name_snapshot or "未归属部门"), ("问题类型汇总", lambda item: item.category_name_snapshot or "未分类")):
        sheet = workbook.create_sheet(title); sheet.append([title.replace("汇总", ""), "考核次数", "处罚金额"])
        totals: dict[str, list] = {}
        for item in effective:
            name = key(item); current = totals.setdefault(name, [0, 0]); current[0] += 1; current[1] += item.penalty_amount
        for name, (count, amount) in sorted(totals.items(), key=lambda item: item[1][1], reverse=True): sheet.append([name, count, amount])
        for row in sheet.iter_rows(min_row=2, min_col=3, max_col=3): row[0].number_format = '#,##0.00'
        sheet.column_dimensions["A"].width = 26; sheet.column_dimensions["B"].width = 14; sheet.column_dimensions["C"].width = 16; style_sheet(sheet)
    output = BytesIO(); workbook.save(output)
    write_audit_log(session, operator_id=user.id, action="assessment.export_excel", target_type="assessment_ledger", target_id="filtered", after={"count": len(records), "status": record_status})
    session.commit()
    return Response(output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=assessment-ledger.xlsx"})
