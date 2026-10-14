from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog


def write_audit_log(session: Session, *, operator_id: int, action: str, target_type: str, target_id: str, before: dict[str, Any] | None = None, after: dict[str, Any] | None = None) -> None:
    session.add(AuditLog(operator_id=operator_id, action=action, target_type=target_type, target_id=target_id, before=before, after=after))
