import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, SessionLocal, engine
from .routers import assessments, auth, documents, exports, management, statistics
from .seed import seed_reference_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # SQLite 仅用于本地开发与测试；生产 PostgreSQL 必须通过 Alembic 执行迁移。
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
        with SessionLocal.begin() as session:
            seed_reference_data(session)
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False, allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type"])
app.include_router(auth.router)
app.include_router(assessments.router)
app.include_router(documents.router)
app.include_router(exports.router)
app.include_router(statistics.router)
app.include_router(management.router)


@app.get("/api/health", tags=["系统"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
