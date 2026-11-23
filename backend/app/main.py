import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import settings
from .db import Base, SessionLocal, engine
from .routers import policies, ai, assessments, auth, documents, exports, management, statistics, quick
from .quick import QuickBodyLimitMiddleware
from .seed import seed_reference_data
from .rule_search import get_index
from . import governance

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_index()  # Build the all-clause local index before accepting paid AI requests.
    # SQLite 仅用于本地开发与测试；生产 PostgreSQL 必须通过 Alembic 执行迁移。
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
        # Local preview predates Alembic. This single nullable column is additive;
        # production always uses the versioned migration above.
        if "ai_catalog_digest" not in {c["name"] for c in inspect(engine).get_columns("quick_submissions")}:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE quick_submissions ADD COLUMN ai_catalog_digest VARCHAR(64)"))
        with SessionLocal.begin() as session:
            seed_reference_data(session)
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False, allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type", "X-Device-Token"])
app.add_middleware(QuickBodyLimitMiddleware)
app.include_router(quick.router)
app.include_router(governance.router)
app.include_router(policies.router)
app.include_router(auth.router)
app.include_router(ai.router)
app.include_router(assessments.router)
app.include_router(documents.router)
app.include_router(exports.router)
app.include_router(statistics.router)
app.include_router(management.router)


@app.get("/api/health", tags=["系统"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
