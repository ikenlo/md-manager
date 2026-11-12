from datetime import datetime

import pytest
from sqlalchemy import select

from app.models import Channel, Setting
from app.services.crypto import decrypt, encrypt


def test_roundtrip():
    token = encrypt("секрет")
    assert token != "секрет" and decrypt(token) == "секрет"


def test_settings_encrypted_and_secret_masked(client, auth, db_session):
    r = client.post(
        "/api/settings",
        headers=auth,
        json={"key": "meta.app_secret", "value": "s3", "is_secret": True},
    )
    assert r.status_code == 200 and r.json()["value"] is None
    client.post("/api/settings", headers=auth, json={"key": "salon.name", "value": "M&D"})
    row = db_session.scalar(select(Setting).where(Setting.key == "meta.app_secret"))
    assert "s3" not in row.value_encrypted and decrypt(row.value_encrypted) == "s3"
    listed = {s["key"]: s["value"] for s in client.get("/api/settings", headers=auth).json()}
    assert listed == {"meta.app_secret": None, "salon.name": "M&D"}


def test_settings_upsert(client, auth):
    for v in ("a", "b"):
        client.post("/api/settings", headers=auth, json={"key": "k", "value": v})
    assert client.get("/api/settings", headers=auth).json() == [
        {"key": "k", "value": "b", "is_secret": False}
    ]


def test_settings_requires_auth(client):
    assert client.post("/api/settings", json={"key": "k", "value": "v"}).status_code == 401


def test_channel_token_encrypted(db_session):
    ch = db_session.scalar(select(Channel))
    ch.set_access_token("EAAG-token")
    db_session.commit()
    assert "EAAG" not in ch.access_token_encrypted
    assert ch.get_access_token() == "EAAG-token"


def test_naive_datetime_rejected(db_session):
    ch = db_session.scalar(select(Channel))
    ch.deleted_at = datetime(2026, 1, 1)
    with pytest.raises(Exception, match="naive"):
        db_session.commit()
    db_session.rollback()
