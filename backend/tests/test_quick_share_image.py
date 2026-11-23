"""分享图片接口：小程序与网页共用，由归档 PDF 渲染，不重新生成正式文书。"""
from io import BytesIO
import struct
import time
import zlib

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.app import documents
from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.models import Assessment
from backend.app.quick import device_hash, limiter
from backend.tests.test_assessment_workflow import quick_payload, reset_database


def a4_pdf(pages: int = 1) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595.28, height=841.89)
    writer.write(output)
    return output.getvalue()


@pytest.fixture(autouse=True)
def fake_libreoffice(monkeypatch):
    monkeypatch.setattr(documents, "convert_word_to_pdf", lambda _: a4_pdf())


def decode_png(content: bytes):
    assert content[:8] == b"\x89PNG\r\n\x1a\n"
    offset, chunks, idat = 8, {}, b""
    while offset < len(content):
        (length,) = struct.unpack(">I", content[offset:offset + 4])
        tag = content[offset + 4:offset + 8]
        data = content[offset + 8:offset + 8 + length]
        (crc,) = struct.unpack(">I", content[offset + 8 + length:offset + 12 + length])
        assert crc == zlib.crc32(tag + data) & 0xFFFFFFFF
        if tag == b"IDAT":
            idat += data
        else:
            chunks[tag] = data
        offset += 12 + length
    assert b"IEND" in chunks
    width, height, depth, color, _, _, _ = struct.unpack(">IIBBBBB", chunks[b"IHDR"])
    return width, height, depth, color, zlib.decompress(idat)


def test_render_pdf_png_produces_a_valid_a4_image():
    width, height, depth, color, raw = decode_png(documents.render_pdf_png(a4_pdf()))
    assert (width, height, depth, color) == (1191, 1684, 8, 2)
    assert len(raw) == height * (1 + width * 3)
    first_row = raw[:1 + width * 3]
    assert first_row[0] == 0 and set(first_row[1:]) == {255}


def test_render_pdf_png_rejects_multi_page_and_corrupt_pdf():
    with pytest.raises(documents.DocumentGenerationError, match="单页"):
        documents.render_pdf_png(a4_pdf(2))
    with pytest.raises(documents.DocumentGenerationError, match="无法读取"):
        documents.render_pdf_png(b"not a pdf")


def test_share_image_is_private_to_the_device_and_only_for_effective_notices():
    reset_database()
    device = {"X-Device-Token": "7" * 64}
    other = {"X-Device-Token": "8" * 64}
    with TestClient(app) as client:
        unit = client.get("/api/quick/config").json()["units"][0]
        created = client.post("/api/quick/assessments", headers=device, json=quick_payload(unit, "5d0f7b0e-55a4-4e44-9d55-2d6f3b1e9a10"))
        assert created.status_code == 200
        item = created.json()
        path = f"/api/quick/assessments/{item['id']}/documents/png"
        image = client.get(path, headers=device)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert "no-store" in image.headers["cache-control"]
        assert image.headers["content-disposition"].startswith("inline")
        assert decode_png(image.content)[:2] == (1191, 1684)
        assert client.get(path, headers=other).status_code == 404
        assert client.get(path).status_code == 401
        assert client.get(f"/api/quick/assessments/{item['id']}/documents/gif", headers=device).status_code == 404
        for kind, signature in (("word", b"PK"), ("pdf", b"%PDF")):
            assert client.get(f"/api/quick/assessments/{item['id']}/documents/{kind}", headers=device).content.startswith(signature)
        with SessionLocal.begin() as session:
            session.get(Assessment, item["id"]).status = "voided"
        assert client.get(path, headers=device).status_code == 409


def test_share_image_rendering_is_rate_limited_per_device():
    reset_database()
    token = "9" * 64
    with TestClient(app) as client:
        unit = client.get("/api/quick/config").json()["units"][0]
        item = client.post("/api/quick/assessments", headers={"X-Device-Token": token}, json=quick_payload(unit, "0e1b6a52-7d4e-4a36-9a3c-4bb0f1e3c2d1")).json()
        limiter.entries["share-image:" + device_hash(token)] = (time.monotonic(), 120)
        try:
            response = client.get(f"/api/quick/assessments/{item['id']}/documents/png", headers={"X-Device-Token": token})
            assert response.status_code == 429
        finally:
            limiter.entries.pop("share-image:" + device_hash(token), None)
