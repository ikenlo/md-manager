"""Бекенд для e2e-тестів: чиста тимчасова БД, демо-дані, mock Meta й Ollama.

Запускає Playwright (webServer у playwright.config.ts). Вручну:
    python e2e/backend.py            (з каталогу frontend; порт E2E_API_PORT, типово 8765)

Кросплатформно (Windows/Linux): шляхи через pathlib, без shell-команд.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND = Path(__file__).resolve().parents[2] / "backend"
PORT = os.environ.get("E2E_API_PORT", "8765")
TMP = Path(tempfile.mkdtemp(prefix="mds-e2e-"))

env = {
    **os.environ,
    "ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "DB_PATH": (TMP / "e2e.db").as_posix(),
    "MEDIA_DIR": (TMP / "media").as_posix(),
    "APP_ENV": "development",
    "ALLOWED_HOSTS": "localhost",
    "LOGIN_RATE_LIMIT": "1000/minute",
    "MOCK_META": "true",
    "MOCK_OLLAMA": "true",
    "OLLAMA_ENABLED": "true",
    "OUTBOUND_INTERVAL_SECONDS": "2",
    "OUTBOUND_RETRY_BASE_SECONDS": "1",
}

SEED_EXTRA = r'''
from sqlalchemy import select
from app.database import SessionLocal
from app.models import AISuggestion, Channel, CrmClient, Dialogue, Message
from app.models.base import utcnow

# Діалоги лише з вихідним повідомленням: simulate_attachment створить у них НОВЕ вхідне —
# так перевіряється автозапуск AI в уже наявному діалозі (simulate_inbound завжди створює новий).
with SessionLocal() as db:
    ig = db.scalar(select(Channel).where(Channel.channel_type == "instagram"))
    for name, handle in [("Авто Один", "auto.one"), ("Авто Два", "auto.two"), ("Авто Три", "auto.three")]:
        d = Dialogue(client=CrmClient(name=name, instagram_handle=handle, meta_ig_user_id=f"ig-{handle}"),
                     channel=ig, status="in_progress", last_message_at=utcnow())
        d.messages = [Message(sender_type="human", content="Вітаємо! Чим допомогти?",
                              direction="outbound", status="sent")]
        db.add(d)
    # Пропозиція із записом: mock Ollama не вміє викликати create_appointment
    d = Dialogue(client=CrmClient(name="Тест Запис", instagram_handle="booking.test", meta_ig_user_id="ig-booking"),
                 channel=ig, status="in_progress", last_message_at=utcnow())
    d.messages = [Message(sender_type="client", content="Хочу записатись на манікюр 1 грудня о 10:00",
                          direction="inbound", status="delivered")]
    db.add(d)
    db.flush()
    booking = {"service_name": "Манікюр", "date": "2026-12-01", "time": "10:00"}
    db.add(AISuggestion(dialogue_id=d.id, message_id=d.messages[0].id, content="Хвилинку, уточнюю деталі.",
                        intent="booking", proposed_booking={"tool": "create_appointment", **booking, "arguments": booking}))
    db.commit()
'''


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=BACKEND, env=env, check=True)


if __name__ == "__main__":
    run("-m", "alembic", "upgrade", "head")
    run("-m", "app.seed", "--demo")
    run("-c", SEED_EXTRA)
    print(f"E2E backend: {TMP} → http://localhost:{PORT}", flush=True)
    uvicorn = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", PORT]
    if os.name == "nt":
        sys.exit(subprocess.call(uvicorn, cwd=BACKEND, env=env))
    # POSIX: процес стає uvicorn — Playwright зупиняє саме його
    os.chdir(BACKEND)
    os.execve(sys.executable, uvicorn, env)
