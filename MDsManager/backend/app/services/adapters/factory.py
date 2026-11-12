from app.config import get_settings
from app.services.adapters.base import MetaAdapter


def get_meta_adapter() -> MetaAdapter:
    if get_settings().mock_meta:
        from app.services.adapters.mock import MockMetaAdapter

        return MockMetaAdapter()
    raise NotImplementedError("Real Meta API in Phase 2.5")
