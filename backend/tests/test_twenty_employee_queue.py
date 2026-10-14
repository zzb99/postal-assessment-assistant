"""SQLite/HTTP admission stress, not production PostgreSQL/LibreOffice capacity evidence."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from backend.app import documents
from backend.app.main import app
from backend.tests.test_assessment_workflow import reset_database


def test_twenty_employees_bounded_queue_retry_and_document_isolation(monkeypatch):
    reset_database()
    def conversion(_):
        time.sleep(.12)
        stream = BytesIO(); pdf = PdfWriter(); pdf.add_blank_page(width=595.28, height=841.89); pdf.write(stream)
        return stream.getvalue()
    monkeypatch.setattr(documents, 'convert_word_to_pdf', conversion)
    with TestClient(app) as client:
        unit = client.get('/api/quick/config').json()['units'][0]
        submissions = [(i, {'X-Device-Token': f'{i:064x}'}, {'request_id': str(uuid4()), 'incident_date': '2026-10-14', 'shift': '白班', 'team': '二班', 'inspector_name': f'职工{i}', 'assessment_unit_id': unit['id'], 'assessment_unit_name': unit['name'], 'quantity': 1, 'assessment_content': '现场问题经核实，按本次事项考核40元。', 'penalty_amount': '40'}) for i in range(1, 21)]
        def generate(item):
            i, headers, payload = item
            return i, client.post('/api/quick/assessments', headers=headers, json=payload)
        with ThreadPoolExecutor(max_workers=20) as pool:
            first = list(pool.map(generate, submissions))
        assert all(response.status_code in (200, 429) for _, response in first), [(i, r.status_code, r.text) for i, r in first]
        results = {i: r.json() for i, r in first if r.status_code == 200}
        for submission in submissions:
            i, headers, payload = submission
            response = client.post('/api/quick/assessments', headers=headers, json=payload)
            assert response.status_code == 200, response.text
            if i in results: assert response.json()['id'] == results[i]['id']
            results[i] = response.json()
        assert len({r['assessment_no'] for r in results.values()}) == 20
        assert all(r['status'] == 'effective' for r in results.values())
        assert client.get(f"/api/quick/assessments/{results[1]['id']}/documents/pdf", headers=submissions[1][1]).status_code == 404
