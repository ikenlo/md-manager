"""Ручна перевірка Gemini тим самим шляхом, що й система (AiRouter, промпт копірайтера салону).

  python scripts/try_gemini.py "Напиши підпис до поста про зимовий догляд за волоссям"
  python scripts/try_gemini.py --image "Холодний блонд у світлому салоні, денне світло" out.jpg

Ключ — GEMINI_API_KEY з .env. Витрати пишуться в тимчасову БД і показуються після відповіді.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.config import Config  # noqa: E402

from alembic import command  # noqa: E402
from app.ai.gemini import GeminiClient, GeminiError  # noqa: E402
from app.ai.router import AiRouter  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db.session import make_engine  # noqa: E402


async def main(argv: list[str]) -> int:
    settings = Settings()
    if not settings.gemini_api_key:
        print("Немає GEMINI_API_KEY у .env")
        return 1
    url = f"sqlite:///{tempfile.mkdtemp()}/try.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    router = AiRouter(make_engine(url), settings, gemini=GeminiClient(settings.gemini_api_key))
    try:
        if argv and argv[0] == "--image":
            img, cost = await router.image(argv[1])
            out = Path(argv[2] if len(argv) > 2 else "gemini.jpg")
            out.write_bytes(img.data)
            print(f"Картинка: {out} · модель {settings.gemini_image_model} · ≈ ${cost:.3f}")
        else:
            r = await router.bulk_text(" ".join(argv))
            print(r.text)
            print(f"\n— {r.provider} · {r.model} · ${r.cost_usd:.5f}")
    except GeminiError as e:
        print(f"Помилка Gemini ({e.status}): {e.message}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
