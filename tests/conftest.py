import pytest
from core.token_cache import _states

@pytest.fixture(autouse=True)
def isolate_token_cache():
    _states.clear()
    yield
    _states.clear()
