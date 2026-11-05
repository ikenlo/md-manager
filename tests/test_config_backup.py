import gzip
import sqlite3

from app.backup import snapshot
from app.config import Settings


def test_env_parsing(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "123, 456")
    monkeypatch.setenv("TG_ADMIN_CHAT_ID", "")
    s = Settings(_env_file=None)
    assert s.admin_ids == [123, 456] and s.tg_admin_chat_id == 0
    monkeypatch.setenv("ADMIN_IDS", "")
    monkeypatch.setenv("TG_ADMIN_CHAT_ID", "-100123")
    s = Settings(_env_file=None)
    assert s.admin_ids == [] and s.tg_admin_chat_id == -100123


def test_backup_snapshot_is_consistent(tmp_path):
    db = tmp_path / "mds.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (x)")
    con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(100)])
    con.commit()  # з'єднання лишається відкритим — як у працюючого бота
    out = snapshot(str(db), str(tmp_path / "b" / "snap.db.gz"))
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(out.read_bytes()))
    assert sqlite3.connect(restored).execute("SELECT count(*) FROM t").fetchone()[0] == 100
    con.close()
