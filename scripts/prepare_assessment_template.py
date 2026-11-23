"""Prepare the server-side DOCX template from the user-approved source file.

This is a build-time helper. It only replaces the five designated fields with
plain placeholders. The content-controls helper then wraps those placeholders
as tagged Word SDTs without rebuilding the document layout.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document


def set_paragraph_text(paragraph, text: str) -> None:
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    document = Document(args.source)
    if len(document.tables) != 1:
        raise RuntimeError("正式模板必须且只能包含一个主表格")
    table = document.tables[0]
    if len(table.rows) != 5:
        raise RuntimeError("正式模板主表格必须包含五行")

    set_paragraph_text(table.cell(0, 1).paragraphs[0], "{{ASSESSMENT_UNIT}}")
    set_paragraph_text(table.cell(1, 1).paragraphs[0], "{{ASSESSMENT_CONTENT}}")
    set_paragraph_text(table.cell(2, 1).paragraphs[0], "{{PENALTY_AMOUNT_CN}}")

    body_paragraphs = [p for p in document.paragraphs if p.text.strip()]
    footer = next((p for p in body_paragraphs if "检查人：" in p.text and "填报日期：" in p.text), None)
    if footer is None:
        raise RuntimeError("未找到检查人/填报日期字段")
    set_paragraph_text(footer, "检查人：{{INSPECTOR_NAME}}       填报日期：{{FILL_DATE}}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    document.save(args.output)


if __name__ == "__main__":
    main()
