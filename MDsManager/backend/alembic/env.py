from logging.config import fileConfig

import app.models  # noqa: F401
from alembic import context
from app.database import Base, engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        # SQLite: batch-режим перестворює таблиці (DROP + rename). З увімкненими FK
        # DROP батьківської таблиці каскадно видалив би дочірні рядки — вимикаємо на час міграції.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()  # SQLAlchemy 2 відкриває транзакцію автоматично — закриваємо
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        if broken:
            raise RuntimeError(f"Порушено зовнішні ключі після міграції: {broken[:5]}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
