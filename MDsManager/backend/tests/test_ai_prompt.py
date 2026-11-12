import pytest

from app.services.ai_prompt import PROMPT_PATH, load_sales_prompt, reload_sales_prompt


def test_prompt_file_exists():
    assert PROMPT_PATH.exists(), f"Prompt file missing: {PROMPT_PATH}"


def test_prompt_loads_successfully():
    content = load_sales_prompt()
    assert len(content) >= 200


def test_prompt_contains_salon_name():
    content = load_sales_prompt()
    assert "M&D" in content


def test_prompt_contains_ukrainian():
    content = load_sales_prompt()
    assert "українською" in content.lower()


def test_prompt_contains_key_rules():
    content = load_sales_prompt()
    assert "НІКОЛИ не записуй" in content
    assert "get_services" in content
    assert "get_slots" in content
    assert "create_appointment" in content


def test_prompt_contains_all_services():
    content = load_sales_prompt()
    services = ["манікюр", "педикюр", "стрижка", "фарбування", "брови"]
    for s in services:
        assert s in content, f"Missing service in prompt: {s}"


def test_prompt_caching_returns_same_object():
    content1 = load_sales_prompt()
    content2 = load_sales_prompt()
    assert content1 is content2


def test_reload_bypasses_cache():
    content1 = load_sales_prompt()
    content2 = reload_sales_prompt()
    assert content1 == content2
    assert content1 is not content2


def test_prompt_missing_raises_file_not_found(tmp_path, monkeypatch):
    fake_path = tmp_path / "nonexistent.md"
    import app.services.ai_prompt as mod

    monkeypatch.setattr(mod, "PROMPT_PATH", fake_path)
    mod.load_sales_prompt.cache_clear()
    with pytest.raises(FileNotFoundError):
        mod.load_sales_prompt()
    mod.load_sales_prompt.cache_clear()


def test_prompt_too_short_raises(tmp_path, monkeypatch):
    short_file = tmp_path / "short.md"
    short_file.write_text("too short", encoding="utf-8")
    import app.services.ai_prompt as mod

    monkeypatch.setattr(mod, "PROMPT_PATH", short_file)
    mod.load_sales_prompt.cache_clear()
    with pytest.raises(ValueError, match="too short"):
        mod.load_sales_prompt()
    mod.load_sales_prompt.cache_clear()
