"""Узгоджений знімок SQLite (без зупинки бота) у gzip.

Шифрування й вивантаження — scripts/backup.sh. Запуск:

python -m app.backup /backups/mds-2026-11-05.db.gz
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from app.config import get_settings


def snapshot(db_path: str, out_path: str) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "snapshot.db"
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        dst = sqlite3.connect(raw)
        try:
            src.backup(dst)  # онлайн-бекап: працює під час запису (WAL)
        finally:
            dst.close()
            src.close()
        check = sqlite3.connect(raw)
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("integrity_check failed")
        finally:
            check.close()
        with raw.open("rb") as f_in, gzip.open(out, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    return out


def main() -> None:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit("Бекап через цей скрипт — лише для SQLite")
    snapshot(url.removeprefix("sqlite:///"), sys.argv[1])
    print(sys.argv[1])


if __name__ == "__main__":
    main()
