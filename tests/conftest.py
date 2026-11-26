import sys
import pytest


@pytest.fixture(autouse=True)
def _preserve_src_modules():
    """Restore any pre-imported src.* modules overwritten by extension-loading tests."""
    saved = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
    yield
    for k, v in saved.items():
        if sys.modules.get(k) is not v:
            sys.modules[k] = v
