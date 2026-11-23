import os
from pathlib import Path
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def migrate(database, target, command="upgrade"):
    environment = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    return subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", command, target], cwd=ROOT, env=environment, capture_output=True, text=True)


def test_fresh_database_can_upgrade_all_migrations(tmp_path):
    result = migrate(tmp_path / "fresh.sqlite", "head")
    assert result.returncode == 0, result.stderr[-3000:]


def test_existing_schema_upgrade_preserves_data_and_device_link_rollback(tmp_path):
    database = tmp_path / "existing.sqlite"
    assert migrate(database, "20260906_02").returncode == 0
    with sqlite3.connect(database) as connection:
        # The legacy initial migration imports current metadata. Simulate the actual old schema.
        connection.execute("DROP TABLE IF EXISTS quick_submissions")
        connection.execute("INSERT INTO departments (name, active, created_at) VALUES (?, 1, ?)", ("历史部门", "2026-10-01 00:00:00"))
    result = migrate(database, "head")
    assert result.returncode == 0, result.stderr[-3000:]
    assert migrate(database, "20260906_02", "downgrade").returncode == 0
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM departments").fetchone()[0] == "历史部门"
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='assessments'").fetchone()
    assert migrate(database, "head").returncode == 0
