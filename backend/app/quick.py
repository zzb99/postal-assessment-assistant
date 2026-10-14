"""No-login intake: private device capability, atomic retry keys and bounded work."""
import hashlib
import json
import re
import secrets
import threading
import time
from collections import OrderedDict

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from .models import User
from .work_queue import BoundedSlot


class QuickBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or not scope["path"].startswith("/api/quick/"):
            return await self.app(scope, receive, send)
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > 16384:
                return await JSONResponse({"detail": "填报内容过大，请缩短后重试"}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


class IntakeLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.entries = OrderedDict()

    def check(self, key: str, limit: int) -> None:
        now = time.monotonic()
        with self.lock:
            while self.entries and next(iter(self.entries.values()))[0] < now - 3600:
                self.entries.popitem(last=False)
            started, count = self.entries.get(key, (now, 0))
            if count >= limit:
                raise HTTPException(status_code=429, detail="提交过于频繁，请稍后再试", headers={"Retry-After": "3600"})
            if key not in self.entries and len(self.entries) >= 4096:
                raise HTTPException(status_code=429, detail="当前访问较多，请稍后再试")
            self.entries[key] = (started, count + 1)


limiter = IntakeLimiter()
ai_limiter = IntakeLimiter()
generation_slot = BoundedSlot(waiting=4)


def device_hash(token: str | None) -> str:
    if not token or not re.fullmatch(r"[a-f0-9]{64}", token):
        raise HTTPException(status_code=401, detail="本机凭证无效，请刷新页面后再试")
    return hashlib.sha256(token.encode()).hexdigest()


def payload_hash(payload) -> str:
    # The expiring AI signature is authorization, not record content; retain old retry hashes.
    data = payload.model_dump(mode="json", exclude={"request_id", "ai_proposal"})
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def intake_actor(session: Session) -> User:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    # This account is an audit actor, not a login credential or a privileged user.
    statement = insert(User).values(username="__quick_intake__", display_name="免登录填报", password_hash=secrets.token_hex(32), role="quick_intake", active=False).on_conflict_do_nothing(index_elements=[User.username])
    session.execute(statement)
    user = session.scalar(select(User).where(User.username == "__quick_intake__"))
    if not user or user.active or user.role != "quick_intake":
        raise HTTPException(status_code=503, detail="免登录填报服务配置异常，请联系管理员")
    return user


def limit_submission(request: Request, owner: str) -> None:
    limiter.check("device:" + owner, 30)
    # Do not trust a client-supplied forwarding header. Shared proxies share this cap.
    limiter.check("peer:" + (request.client.host if request.client else "unknown"), 300)
