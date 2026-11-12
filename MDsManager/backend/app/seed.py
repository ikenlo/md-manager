"""Перший адміністратор (+ демо-діалоги з --demo).

python -m app.seed [--demo]
"""

import argparse
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Agent, Channel, CrmClient, DialogTag, Dialogue, Message, User
from app.models.base import utcnow
from app.services.auth import hash_password

log = logging.getLogger("seed")

ADMIN_EMAIL = "admin@mds.local"
ADMIN_PASSWORD = "admin"
ADMIN_NAME = "Директор"


def seed_admin(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    if user:
        log.info("Користувач %s вже існує — пропускаю", ADMIN_EMAIL)
        return user
    user = User(
        email=ADMIN_EMAIL,
        password_hash=hash_password(ADMIN_PASSWORD),
        display_name=ADMIN_NAME,
        role="director",
        is_active=True,
    )
    db.add(user)
    db.commit()
    log.info("Створено користувача %s", ADMIN_EMAIL)
    return user


DEMO = [
    (
        "Олена Коваль",
        "olena.koval",
        "instagram",
        "in_progress",
        ["манікюр"],
        [
            ("client", "Добрий день! Чи є вільні віконця на манікюр у суботу?"),
            (
                "agent",
                "Вітаю, Олено! У суботу є 11:00 та 15:30 у майстра Ірини. Який час зручніший?",
            ),
            ("client", "15:30 підходить 🙌"),
        ],
    ),
    (
        "Марія Шевчук",
        "masha_sh",
        "telegram",
        "new",
        ["брови"],
        [
            ("client", "Скільки коштує корекція брів?"),
        ],
    ),
    (
        "Анна Бондар",
        "anna.bond",
        "facebook",
        "ordered",
        ["стрижка"],
        [
            ("client", "Хочу записатися на стрижку"),
            ("agent", "Записала вас на четвер, 14:00. Чекаємо!"),
        ],
    ),
]


def seed_demo(db: Session) -> None:
    if db.scalar(select(Dialogue.id).limit(1)):
        log.info("Діалоги вже є — демо пропускаю")
        return
    agent = Agent(name="Аліна (AI)", role="sales", system_prompt="", is_active=True)
    db.add(agent)
    channels: dict[str, Channel] = {}
    for t, name in (
        ("instagram", "@md.salon"),
        ("telegram", "@md_salon_bot"),
        ("facebook", "M&D Salon"),
    ):
        channels[t] = Channel(channel_type=t, account_name=name, status="mock")
        db.add(channels[t])
    now = utcnow()
    for i, (name, handle, ch, status, tags, msgs) in enumerate(DEMO):
        client = CrmClient(name=name, instagram_handle=handle)
        # демо-ідентифікатори Meta — щоб MockMetaAdapter мав кому «відправляти»
        if ch == "instagram":
            client.meta_ig_user_id = f"demo-ig-{handle}"
        elif ch == "facebook":
            client.meta_fb_user_id = f"demo-fb-{handle}"
        d = Dialogue(
            client=client,
            channel=channels[ch],
            assigned_agent=agent,
            status=status,
            last_message_at=now - timedelta(minutes=10 * i),
        )
        d.tags = [DialogTag(tag_name=t) for t in tags]
        base = now - timedelta(minutes=10 * i + len(msgs))
        d.messages = [
            Message(
                sender_type=s,
                content=c,
                created_at=base + timedelta(minutes=k),
                direction="inbound" if s == "client" else "outbound",
                status="delivered" if s == "client" else "sent",
            )
            for k, (s, c) in enumerate(msgs)
        ]
        inbound = [m.created_at for m in d.messages if m.direction == "inbound"]
        outbound = [m.created_at for m in d.messages if m.direction == "outbound"]
        d.last_inbound_at = max(inbound) if inbound else None
        d.last_outbound_at = max(outbound) if outbound else None
        db.add(d)
    db.commit()
    log.info("Додано %d демо-діалоги", len(DEMO))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Початкові дані MDs Manager")
    parser.add_argument("--demo", action="store_true", help="додати демо-діалоги")
    args = parser.parse_args()
    with SessionLocal() as db:
        seed_admin(db)
        if args.demo:
            seed_demo(db)


if __name__ == "__main__":
    main()
