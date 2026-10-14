param(
  [string]$Python = $env:ASSESSMENT_PYTHON
)

if (-not $Python) { $Python = "python" }
& $Python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
