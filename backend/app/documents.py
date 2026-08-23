from datetime import date
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Assessment


def format_cn_date(value: date) -> str:
    return f"{value.year}年{value.month}月{value.day}日"


def _set_cell_text(cell, text: str, bold: bool = False) -> None:
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(10.5)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _set_cell_border(cell, **kwargs) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right"):
        tag = "w:" + edge
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), kwargs.get(edge, "single"))
        element.set(qn("w:sz"), "8")
        element.set(qn("w:color"), "000000")


def build_word(assessment: Assessment) -> bytes:
    document = Document()
    section = document.sections[0]
    section.top_margin = Cm(1.8); section.bottom_margin = Cm(1.8); section.left_margin = Cm(2.1); section.right_margin = Cm(2.1)
    style = document.styles["Normal"]
    style.font.name = "Microsoft YaHei"; style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei"); style.font.size = Pt(10.5)
    title = document.add_paragraph(); title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("邮件处理中心"); run.bold = True; run.font.name = "Microsoft YaHei"; run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei"); run.font.size = Pt(20)
    subtitle = document.add_paragraph(); subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("通信生产考核通知单"); run.bold = True; run.font.name = "Microsoft YaHei"; run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei"); run.font.size = Pt(15)
    number = document.add_paragraph(); number.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    number.add_run(f"考核编号：{assessment.assessment_no or '草稿'}")
    rows = [
        ("被考核工段", assessment.assessment_unit_name_snapshot),
        ("发生日期 / 班次", f"{format_cn_date(assessment.incident_date)} / {assessment.shift}"),
        ("问题类型 / 作业环节", f"{assessment.category_name_snapshot or '未分类'} / {assessment.operation_stage or '未填写'}"),
        ("考核事项", assessment.assessment_content),
        ("处罚金额", f"人民币 {assessment.penalty_amount:.2f} 元（{assessment.penalty_amount_cn}）"),
        ("被处罚单位/人员意见", ""),
        ("业务主管复核意见", ""),
        ("负责人意见", ""),
        ("备注", assessment.remark or ""),
    ]
    table = document.add_table(rows=0, cols=2)
    table.autofit = False
    table.columns[0].width = Cm(3.2); table.columns[1].width = Cm(13.4)
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].width = Cm(3.2); cells[1].width = Cm(13.4)
        _set_cell_text(cells[0], label, True); _set_cell_text(cells[1], value)
        for cell in cells: _set_cell_border(cell)
        if label in {"考核事项", "被处罚单位/人员意见", "业务主管复核意见", "负责人意见", "备注"}:
            cells[0].paragraphs[0].paragraph_format.space_after = Pt(28)
            cells[1].paragraphs[0].paragraph_format.space_after = Pt(28)
    footer = document.add_paragraph(); footer.paragraph_format.space_before = Pt(12)
    footer.add_run(f"检查人：{assessment.inspector_name}    填报日期：{format_cn_date(assessment.finalized_at.date() if assessment.finalized_at else assessment.created_at.date())}")
    version = document.add_paragraph(); version.add_run(f"考核办法版本：{assessment.regulation_version or '未填写'}")
    output = BytesIO(); document.save(output); return output.getvalue()


def build_pdf(assessment: Assessment) -> bytes:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("CNBody", parent=styles["BodyText"], fontName="STSong-Light", fontSize=10.5, leading=18)
    small = ParagraphStyle("CNSmall", parent=body, fontSize=9.5, leading=15)
    title = ParagraphStyle("CNTitle", parent=body, fontSize=20, leading=28, alignment=TA_CENTER)
    subtitle = ParagraphStyle("CNSubtitle", parent=body, fontSize=15, leading=23, alignment=TA_CENTER)
    story = [Paragraph("邮件处理中心", title), Paragraph("通信生产考核通知单", subtitle), Spacer(1, 4 * mm), Paragraph(f"考核编号：{assessment.assessment_no or '草稿'}", small), Spacer(1, 3 * mm)]
    def pair(label: str, value: str):
        table = Table([[Paragraph(label, body), Paragraph(value.replace("\n", "<br/>") or "&nbsp;", body)]], colWidths=[35 * mm, 135 * mm])
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F2F4F7")), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        story.append(table)
    pair("被考核工段", assessment.assessment_unit_name_snapshot)
    pair("发生日期 / 班次", f"{format_cn_date(assessment.incident_date)} / {assessment.shift}")
    pair("问题类型 / 作业环节", f"{assessment.category_name_snapshot or '未分类'} / {assessment.operation_stage or '未填写'}")
    story.extend([Spacer(1, 3 * mm), Paragraph("考核事项", body), Spacer(1, 1 * mm), Paragraph(assessment.assessment_content.replace("\n", "<br/>"), body), Spacer(1, 4 * mm)])
    pair("处罚金额", f"人民币 {assessment.penalty_amount:.2f} 元（{assessment.penalty_amount_cn}）")
    for label in ("被处罚单位/人员意见", "业务主管复核意见", "负责人意见"):
        pair(label, "<br/><br/><br/>")
    pair("备注", assessment.remark or "")
    story.extend([Spacer(1, 4 * mm), Paragraph(f"检查人：{assessment.inspector_name}　　填报日期：{format_cn_date(assessment.finalized_at.date() if assessment.finalized_at else assessment.created_at.date())}", body), Paragraph(f"考核办法版本：{assessment.regulation_version or '未填写'}", small)])
    document.build(story)
    return output.getvalue()
