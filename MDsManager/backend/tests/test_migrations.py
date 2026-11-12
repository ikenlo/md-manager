"""Міграції на справжньому файлі SQLite: схема = моделі, downgrade не губить дані."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.database import Base

BACKEND = Path(__file__).resolve().parent.parent


def alembic(db: Path, *args: str) -> None:
    env = {**os.environ, "DB_PATH": db.as_posix()}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "mig.db"


def test_head_matches_models(db_file):
    alembic(db_file, "upgrade", "head")
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []


def test_0002_backfills_and_downgrade_keeps_data(db_file):
    alembic(db_file, "upgrade", "0001")
    con = sqlite3.connect(db_file)
    con.executescript(
        """
        INSERT INTO crm_clients (id, uuid, name, total_spent, visits_count, created_at, updated_at)
          VALUES (1, 'c1', 'Олена', 0, 0, '2026-11-01 10:00:00', '2026-11-01 10:00:00');
        INSERT INTO channels (id, uuid, channel_type, account_name, status, created_at, updated_at)
          VALUES (1, 'ch1', 'instagram', 'md', 'connected',
                  '2026-11-01 10:00:00', '2026-11-01 10:00:00');
        INSERT INTO dialogues (id, uuid, client_id, channel_id, status, created_at, updated_at)
          VALUES (1, 'd1', 1, 1, 'new', '2026-11-01 10:00:00', '2026-11-01 10:00:00');
        INSERT INTO dialog_tags (id, uuid, dialogue_id, tag_name, created_at, updated_at)
          VALUES (1, 't1', 1, 'манікюр', '2026-11-01 10:00:00', '2026-11-01 10:00:00');
        INSERT INTO messages (id, uuid, dialogue_id, sender_type, content, created_at) VALUES
          (1, 'm1', 1, 'client', 'Привіт', '2026-11-01 10:00:00'),
          (2, 'm2', 1, 'agent', 'Вітаю!', '2026-11-01 10:01:00'),
          (3, 'm3', 1, 'client', 'Дякую', '2026-11-01 10:05:00');
        """
    )
    con.commit()
    con.close()

    alembic(db_file, "upgrade", "head")
    con = sqlite3.connect(db_file)
    rows = con.execute("SELECT id, direction, status FROM messages ORDER BY id").fetchall()
    assert rows == [
        (1, "inbound", "delivered"),
        (2, "outbound", "sent"),
        (3, "inbound", "delivered"),
    ]
    assert con.execute(
        "SELECT last_inbound_at, last_outbound_at, unread_count FROM dialogues"
    ).fetchone() == ("2026-11-01 10:05:00", "2026-11-01 10:01:00", 0)
    assert con.execute("SELECT webhook_status FROM channels").fetchone() == ("inactive",)
    assert con.execute("SELECT is_anonymous FROM crm_clients").fetchone() == (0,)
    con.close()

    # SQLite перестворює таблиці при drop_column — FK-каскад не має з'їсти дочірні рядки
    alembic(db_file, "downgrade", "0001")
    con = sqlite3.connect(db_file)
    assert con.execute("SELECT count(*) FROM messages").fetchone() == (3,)
    assert con.execute("SELECT count(*) FROM dialog_tags").fetchone() == (1,)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not {"outbound_queue", "media_assets"} & tables
    cols = {r[1] for r in con.execute("PRAGMA table_info(messages)")}
    assert "direction" not in cols
    con.close()

    alembic(db_file, "upgrade", "head")
