"""Змінити пароль користувача й завершити всі його сесії.

python -m app.set_password admin@mds.local
"""

import argparse
import getpass
import sys

from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import User, UserSession
from app.services.auth import hash_password

MIN_LENGTH = 12


def set_password(db, email: str, password: str) -> bool:
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if user is None:
        return False
    user.password_hash = hash_password(password)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Змінити пароль користувача MDs Manager")
    parser.add_argument("email")
    args = parser.parse_args()
    password = getpass.getpass("Новий пароль: ")
    if len(password) < MIN_LENGTH:
        sys.exit(f"Пароль має містити щонайменше {MIN_LENGTH} символів")
    if password != getpass.getpass("Повторіть пароль: "):
        sys.exit("Паролі не збігаються")
    with SessionLocal() as db:
        if not set_password(db, args.email, password):
            sys.exit(f"Користувача {args.email} не знайдено")
    print("Пароль змінено, усі сесії завершено")  # noqa: T201 — CLI


if __name__ == "__main__":
    main()
