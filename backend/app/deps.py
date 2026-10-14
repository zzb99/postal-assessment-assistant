from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_session
from .models import User
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    user = session.get(User, decode_access_token(credentials.credentials))
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已停用")
    if user.role not in {"admin", "leader", "department_manager", "employee"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号角色无效，请联系管理员")
    if user.role in {"department_manager", "employee"} and user.department_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号未绑定部门，请联系管理员")
    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限执行此操作")
        return user
    return checker


def assert_record_scope(user: User, department_id: int | None, created_by: int | None = None) -> None:
    if user.role in {"admin", "leader"}:
        return
    if user.department_id is not None and user.department_id == department_id and (
        user.role == "department_manager" or (user.role == "employee" and created_by == user.id)
    ):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该部门考核记录")
