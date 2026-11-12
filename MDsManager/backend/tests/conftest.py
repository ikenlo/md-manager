import os

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["DB_PATH"] = ":memory:"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.database import Base, _set_sqlite_pragmas, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_admin, seed_demo  # noqa: E402
from app.services.rate_limit import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def db_session():
    from sqlalchemy import create_engine, event

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    event.listen(engine, "connect", _set_sqlite_pragmas)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as s:
        seed_admin(s)
        seed_demo(s)
        yield s
    engine.dispose()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, base_url="http://localhost") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/login", json={"email": "admin@mds.local", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}
