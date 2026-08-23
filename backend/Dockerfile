FROM python:3.12-slim

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_DEFAULT_TIMEOUT=120

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=${PIP_DEFAULT_TIMEOUT}

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --retries 10 --index-url "${PIP_INDEX_URL}" -r /app/backend/requirements.txt
COPY backend /app/backend

EXPOSE 8000
CMD ["sh", "-c", "python -m alembic -c backend/alembic.ini upgrade head && python -m backend.app.seed && python -m backend.app.bootstrap && exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 2"]
