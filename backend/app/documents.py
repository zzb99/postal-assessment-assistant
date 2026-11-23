from __future__ import annotations

import hashlib
import shutil
import struct
import subprocess
import tempfile
import threading
import uuid
import zipfile
import zlib
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from lxml import etree
from pypdf import PdfReader

from .config import settings
from .models import Assessment

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
REQUIRED_TEMPLATE_TAGS = {
    "ASSESSMENT_UNIT",
    "ASSESSMENT_CONTENT",
    "PENALTY_AMOUNT_CN",
    "INSPECTOR_NAME",
    "FILL_DATE",
}
_CONVERSION_SEMAPHORE = threading.BoundedSemaphore(value=1)


class DocumentGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArchivedFiles:
    docx_path: str
    pdf_path: str
    docx_sha256: str
    pdf_sha256: str
    template_sha256: str
    generated_at: datetime
    archive_dir: Path


def qn(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def format_cn_date(value) -> str:
    return f"{value.year}年{value.month}月{value.day}日"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _new_run(text: str, rpr: etree._Element | None, *, break_before: bool = False) -> etree._Element:
    run = etree.Element(qn("r"))
    if rpr is not None:
        run.append(deepcopy(rpr))
    if break_before:
        etree.SubElement(run, qn("br"))
    text_node = etree.SubElement(run, qn("t"))
    text_node.text = text
    if text.startswith(" ") or text.endswith(" "):
        text_node.set(XML_SPACE, "preserve")
    return run


def _fill_sdt(sdt: etree._Element, value: str) -> None:
    content = sdt.find("w:sdtContent", namespaces=NS)
    if content is None:
        raise DocumentGenerationError("Word模板内容控件缺少内容区域")
    rpr = content.find(".//w:rPr", namespaces=NS)
    for child in list(content):
        content.remove(child)
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(lines):
        content.append(_new_run(line, rpr, break_before=index > 0))


def _fill_body(sdt: etree._Element, value: str) -> None:
    """Real paragraphs, not line breaks inside one run, retaining the template style."""
    paragraph = sdt.getparent()
    cell = paragraph.getparent()
    props = paragraph.find('w:pPr', NS)
    rpr = props.find('w:rPr', NS) if props is not None else None
    parts = [part.strip() for part in value.replace('\r', '').split('\n') if part.strip()]
    if not parts or len(parts) > 3:
        raise DocumentGenerationError('正文请保持事实依据、整改要求两段式，最多三段')
    _fill_sdt(sdt, parts[0])
    previous = paragraph
    inserted = [paragraph]
    for part in parts[1:]:
        following = etree.Element(qn('p'))
        if props is not None: following.append(deepcopy(props))
        following.append(_new_run(part, rpr))
        cell.insert(cell.index(previous) + 1, following)
        inserted.append(following)
        previous = following
    # Short texts retain the original formal-document size. Longer texts use
    # bounded local fitting; no truncation, signature rows remain untouched.
    size = 0 if len(value) <= 240 else 26 if len(value) <= 340 else 23 if len(value) <= 480 else 22
    if size:
        for p in inserted:
            for run in p.findall('.//w:r', NS):
                style = run.find('w:rPr', NS)
                if style is None:
                    style = etree.Element(qn('rPr'))
                    run.insert(0, style)
                for name in ('sz','szCs'):
                    node=style.find(f'w:{name}', NS)
                    if node is None: node=etree.SubElement(style, qn(name))
                    node.set(qn('val'), str(size))


def build_word(assessment: Assessment, *, fill_time: datetime | None = None) -> bytes:
    template_path = settings.document_template
    if not template_path.is_file():
        raise DocumentGenerationError(f"Word模板不存在：{template_path.name}")
    template = template_path.read_bytes()
    fill_time = fill_time or datetime.now(ZoneInfo("Asia/Shanghai"))
    if fill_time.tzinfo is None:
        fill_time = fill_time.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    values = {
        "ASSESSMENT_UNIT": assessment.assessment_unit_name_snapshot,
        "ASSESSMENT_CONTENT": assessment.assessment_content,
        "PENALTY_AMOUNT_CN": assessment.penalty_amount_cn,
        "INSPECTOR_NAME": f"{assessment.team}{assessment.inspector_name}",
        "FILL_DATE": format_cn_date(fill_time.astimezone(ZoneInfo("Asia/Shanghai")).date()),
    }
    footer_width = sum(1 if ord(c) > 127 else .55 for c in values['INSPECTOR_NAME'])
    if footer_width > 10:
        raise DocumentGenerationError('班组与检查人合计过长，超过模板单行容量；请使用规范短称，不会自动缩小字体')

    source = BytesIO(template)
    output = BytesIO()
    found: dict[str, int] = {}
    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "word/document.xml":
                parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
                root = etree.fromstring(content, parser)
                for sdt in root.xpath(".//w:sdt", namespaces=NS):
                    tag = sdt.xpath("string(.//w:sdtPr/w:tag/@w:val)", namespaces=NS)
                    if tag in values:
                        found[tag] = found.get(tag, 0) + 1
                        if tag == 'ASSESSMENT_CONTENT': _fill_body(sdt, values[tag])
                        else: _fill_sdt(sdt, values[tag])
                content = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
            zout.writestr(item, content)

    invalid = sorted(tag for tag in REQUIRED_TEMPLATE_TAGS if found.get(tag) != 1)
    if invalid:
        raise DocumentGenerationError(f"Word模板字段标记异常：{', '.join(invalid)}")
    return output.getvalue()


def _verify_pdf(content: bytes) -> None:
    if not content.startswith(b"%PDF"):
        raise DocumentGenerationError("LibreOffice未生成有效PDF")
    try:
        reader = PdfReader(BytesIO(content))
        if len(reader.pages) != 1:
            raise DocumentGenerationError("正式文书必须保持一页A4")
        box = reader.pages[0].mediabox
        width, height = float(box.width), float(box.height)
        if abs(width - 595.28) > 4 or abs(height - 841.89) > 4:
            raise DocumentGenerationError("转换后的PDF不是A4页面")
    except DocumentGenerationError:
        raise
    except Exception as error:
        raise DocumentGenerationError("无法验证转换后的PDF") from error


def convert_word_to_pdf(docx_content: bytes) -> bytes:
    with _CONVERSION_SEMAPHORE:
        with tempfile.TemporaryDirectory(prefix="assessment-convert-") as temp:
            temp_dir = Path(temp)
            docx_path = temp_dir / "assessment.docx"
            output_dir = temp_dir / "output"
            profile_dir = temp_dir / "profile"
            output_dir.mkdir()
            profile_dir.mkdir()
            docx_path.write_bytes(docx_content)
            command = [
                settings.libreoffice_binary,
                "--headless",
                "--norestore",
                "--nodefault",
                "--nolockcheck",
                f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                str(output_dir),
                str(docx_path),
            ]
            try:
                completed = subprocess.run(command, capture_output=True, timeout=settings.libreoffice_timeout_seconds, check=False)
            except FileNotFoundError as error:
                raise DocumentGenerationError("服务器未安装LibreOffice，文书保持草稿") from error
            except subprocess.TimeoutExpired as error:
                raise DocumentGenerationError("Word转PDF超过60秒，文书保持草稿") from error
            pdf_path = output_dir / "assessment.pdf"
            if completed.returncode != 0 or not pdf_path.is_file():
                detail = (completed.stderr or completed.stdout).decode("utf-8", errors="replace").strip()[-500:]
                raise DocumentGenerationError(f"Word转PDF失败，文书保持草稿：{detail or '未生成文件'}")
            content = pdf_path.read_bytes()
            _verify_pdf(content)
            return content


def archive_documents(assessment: Assessment, generated_at: datetime) -> ArchivedFiles:
    if not assessment.assessment_no:
        raise DocumentGenerationError("正式编号尚未生成")
    root = settings.document_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    staging_root = root / ".staging"
    staging_root.mkdir(exist_ok=True)
    staging_dir = staging_root / uuid.uuid4().hex
    final_dir = root / assessment.incident_date.strftime("%Y") / assessment.incident_date.strftime("%m") / assessment.assessment_no
    if final_dir.exists():
        raise DocumentGenerationError("该考核编号的归档目录已存在，禁止覆盖")
    staging_dir.mkdir()
    try:
        docx_content = build_word(assessment, fill_time=generated_at)
        pdf_content = convert_word_to_pdf(docx_content)
        docx_name = f"{assessment.assessment_no}.docx"
        pdf_name = f"{assessment.assessment_no}.pdf"
        (staging_dir / docx_name).write_bytes(docx_content)
        (staging_dir / pdf_name).write_bytes(pdf_content)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_dir.replace(final_dir)
        return ArchivedFiles(
            docx_path=(final_dir / docx_name).relative_to(root).as_posix(),
            pdf_path=(final_dir / pdf_name).relative_to(root).as_posix(),
            docx_sha256=_sha256(docx_content),
            pdf_sha256=_sha256(pdf_content),
            template_sha256=_sha256(settings.document_template.read_bytes()),
            generated_at=generated_at,
            archive_dir=final_dir,
        )
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def cleanup_archive(path: Path | None) -> None:
    if path is None:
        return
    root = settings.document_root.resolve()
    resolved = path.resolve()
    if root in resolved.parents and resolved.name.startswith("KH-"):
        shutil.rmtree(resolved, ignore_errors=True)


def read_archived_file(relative_path: str, expected_sha256: str) -> bytes:
    root = settings.document_root.resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise DocumentGenerationError("归档文书不存在")
    content = path.read_bytes()
    if _sha256(content) != expected_sha256:
        raise DocumentGenerationError("归档文书哈希校验失败，禁止下载")
    return content


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def render_pdf_png(pdf_content: bytes, scale: float = 2.0) -> bytes:
    """把已归档且已校验哈希的单页 PDF 渲染为 PNG，供微信小程序和网页分享图片。

    只读取归档 PDF，不重新生成或修改正式文书；图片由 pdfium 渲染，PNG 用标准库编码，不额外依赖图像库。
    """
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(pdf_content)
    except Exception as error:  # pdfium 对损坏文件抛出自身异常类型
        raise DocumentGenerationError("归档PDF无法读取，不能生成分享图片") from error
    try:
        if len(document) != 1:
            raise DocumentGenerationError("正式文书不是单页，不能生成分享图片")
        page = document[0]
        try:
            bitmap = page.render(scale=scale, rev_byteorder=True)
            try:
                width, height, stride, channels = bitmap.width, bitmap.height, bitmap.stride, bitmap.n_channels
                pixels = memoryview(bitmap.buffer).cast("B")
                row = width * channels
                raw = b"".join(b"\x00" + pixels[offset:offset + row].tobytes() for offset in range(0, height * stride, stride))
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()
    color_type = {1: 0, 3: 2, 4: 6}.get(channels)
    if color_type is None:
        raise DocumentGenerationError("分享图片颜色格式不受支持")
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(raw, 6)) + _png_chunk(b"IEND", b"")
