from functools import lru_cache
from pathlib import Path

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "sales_agent.md"


@lru_cache(maxsize=1)
def load_sales_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"System prompt not found: {PROMPT_PATH}")
    content = PROMPT_PATH.read_text(encoding="utf-8").strip()
    if len(content) < 200:
        raise ValueError(f"System prompt too short ({len(content)} chars)")
    return content


def reload_sales_prompt() -> str:
    load_sales_prompt.cache_clear()
    return load_sales_prompt()
