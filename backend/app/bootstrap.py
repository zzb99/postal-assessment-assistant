"""首次部署初始化：通过环境变量创建管理员，避免在代码中固化弱密码。"""
import os

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import Department, User
from .security import hash_password


def run() -> None:
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    display_name = os.getenv("BOOTSTRAP_ADMIN_DISPLAY_NAME", "系统管理员").strip() or "系统管理员"
    if not username or not password:
        raise SystemExit("请设置 BOOTSTRAP_ADMIN_USERNAME 与 BOOTSTRAP_ADMIN_PASSWORD 后再初始化。")
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        existing = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing:
            print(f"管理员 {username} 已存在，未修改。")
            return
        department = session.execute(select(Department).where(Department.name == "邮件处理中心")).scalar_one_or_none()
        if not department:
            department = Department(name="邮件处理中心")
            session.add(department)
            session.flush()
        session.add(User(username=username, display_name=display_name, password_hash=hash_password(password), role="admin", department_id=department.id))
    print(f"管理员 {username} 已创建。")


if __name__ == "__main__":
    run()
