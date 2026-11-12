from app.config import get_settings
from app.services.adapters.base import MetaAdapter
from app.services.adapters.ollama_base import OllamaAdapter, OllamaDisabledError


def get_meta_adapter() -> MetaAdapter:
    if get_settings().mock_meta:
        from app.services.adapters.mock import MockMetaAdapter

        return MockMetaAdapter()
    raise NotImplementedError("Real Meta API in Phase 2.5")


def get_ollama_adapter() -> OllamaAdapter:
    cfg = get_settings()
    if not cfg.ollama_enabled:
        raise OllamaDisabledError("Ollama disabled (OLLAMA_ENABLED=false)")
    if cfg.mock_ollama:
        from app.services.adapters.ollama_mock import MockOllamaAdapter

        return MockOllamaAdapter()
    from app.services.adapters.ollama_real import RealOllamaAdapter

    return RealOllamaAdapter()
