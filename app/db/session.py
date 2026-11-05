"""Двигун і сесії БД."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def make_engine(url: str) -> Engine:
    is_sqlite = url.startswith("sqlite")
    if is_sqlite and ":memory:" not in url:
        Path(url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 15} if is_sqlite else {},
    )
    if is_sqlite:
        _configure_sqlite(engine)
    return engine


def _configure_sqlite(engine: Engine) -> None:
    # Вимикаємо автоматичний BEGIN драйвера pysqlite, щоб самим керувати
    # транзакціями (BEGIN IMMEDIATE для запису) — рецепт з документації SQLAlchemy.
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # noqa: ANN001
        dbapi_conn.isolation_level = None
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):  # noqa: ANN001
        if conn.info.pop("immediate", False):
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            conn.exec_driver_sql("BEGIN")


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
        _SessionLocal = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    with get_sessionmaker()() as s, s.begin():
        yield s


@contextmanager
def write_transaction(engine: Engine | None = None) -> Iterator[Session]:
    """Транзакція на запис з блокуванням бази (SQLite: BEGIN IMMEDIATE).

    Дві такі транзакції не можуть одночасно прочитати «слот вільний» і обидві
    вставити запис: друга чекає, доки перша не закомітиться, і тоді бачить її
    запис. У Postgres подвійний запис додатково ловить exclusion constraint.
    """
    engine = engine or get_engine()
    with engine.connect() as conn:
        if conn.dialect.name == "sqlite":
            conn.info["immediate"] = True
        try:
            with Session(bind=conn, expire_on_commit=False) as s:
                yield s
                s.commit()
        finally:
            conn.info.pop("immediate", None)
