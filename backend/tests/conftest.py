"""Never allow pytest to charge a real AI account or open the preview database."""
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

Path(".pytest_cache").mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///./.pytest_cache/backend-test-{os.getpid()}.sqlite"
os.environ["JWT_SECRET"] = "test-only-jwt-secret-must-be-at-least-32-bytes"
os.environ["DOCUMENT_ROOT"] = str((Path(".pytest_cache") / f"documents-{os.getpid()}").resolve())
os.environ["DEEPSEEK_API_KEY"] = "mock-key-not-a-real-credential"
os.environ["REQUIRE_TRUSTED_DEVICE"] = "false"  # Legacy regression profile; new authorization tests enable it.
os.environ["REQUIRE_POLICY_APPROVAL"] = "false"


@pytest.fixture(autouse=True)
def forbid_real_paid_ai(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Real paid AI is forbidden in tests; mock httpx.post or _chat")
    monkeypatch.setattr(httpx, "post", blocked)


@pytest.fixture(autouse=True)
def ensure_test_metadata():
    from backend.app.db import Base, engine
    from backend.app import models
    Base.metadata.create_all(engine)


@pytest.fixture
def policy_today(monkeypatch):
    """把制度模块的“今天”（北京时间）改成指定日期，时钟照常往前走。

    恢复旧版制度从恢复当天起生效，涉及恢复的断言因此和运行日期有关；
    固定日期后，这些测试哪天运行结果都一样。
    """
    from backend.app import policy_store

    def move_to(day: date) -> None:
        shift = datetime.now(ZoneInfo("Asia/Shanghai")).date() - day

        class ShiftedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) - shift

        monkeypatch.setattr(policy_store, "datetime", ShiftedClock)

    return move_to
