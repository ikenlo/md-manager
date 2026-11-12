from datetime import time

import pytest
from alembic.config import Config
from sqlalchemy.orm import Session

from alembic import command
from app.db.models import Client, Master, Service, WorkSchedule
from app.db.session import make_engine


@pytest.fixture
def engine(tmp_path):
    """Файлова SQLite (не :memory:) — щоб кілька потоків бачили одну базу."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    eng = make_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def salon(engine):
    """Один майстер (щодня 09–18), дві послуги, один клієнт."""
    with Session(engine, expire_on_commit=False) as s, s.begin():
        cut = Service(name="Стрижка", price_from=600, duration_min=60, buffer_min=15)
        nails = Service(name="Манікюр", price_from=500, duration_min=90, buffer_min=0)
        m = Master(name="Маргарита", services=[cut])
        m.schedule = [
            WorkSchedule(weekday=d, start_time=time(9), end_time=time(18)) for d in range(7)
        ]
        c1 = Client(name="Олена")
        c2 = Client(name="Ірина")
        s.add_all([cut, nails, m, c1, c2])
    return {"cut": cut, "nails": nails, "master": m, "c1": c1, "c2": c2}
