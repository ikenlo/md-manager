# MDs manager

AI-адміністратор салону M&D: Instagram Direct і Telegram, запис до майстра,
нагадування, передача складних діалогів людині. Специфікація — [docs/SPEC.md](docs/SPEC.md).

## Стан

| Етап | Що | Стан |
|---|---|---|
| 1 | Каркас, моделі, міграція, seed | ✅ |
| 2 | Алгоритм слотів, create_booking, тест гонки | ✅ |
| 3 | Telegram-бот + адмінка | — |
| 4 | AI-агент | — |
| 5 | Instagram | — |
| 6 | Нагадування і handoff | — |
| 7 | Деплой | — |

## Локальний запуск

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env              # для локальної роботи DATABASE_URL=sqlite:///./data/mds.db
alembic upgrade head
python seed.py                    # приклад даних — замініть seed.yaml на реальні
pytest
uvicorn app.main:app --reload     # GET /health
```
