from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Master, SalonSetting, Service, WorkSchedule
from seed import seed


def test_seed_is_idempotent(engine):
    data = yaml.safe_load(Path("seed.yaml").read_text(encoding="utf-8"))
    for _ in range(2):
        with Session(engine) as s, s.begin():
            seed(s, data)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Service)) == len(data["services"])
        assert s.scalar(select(func.count()).select_from(Master)) == len(data["masters"])
        expected_shifts = sum(len(m["schedule"]) for m in data["masters"])
        assert s.scalar(select(func.count()).select_from(WorkSchedule)) == expected_shifts
        assert s.get(SalonSetting, "salon_name").value == "M&D"
        m = s.scalar(select(Master).where(Master.name == data["masters"][0]["name"]))
        assert {x.name for x in m.services} == set(data["masters"][0]["services"])
