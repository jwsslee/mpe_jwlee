from core.api import APIError,KIS,KRX
import core.settings as config
from test_system import app,login


def test_old_loaded_settings_schema_is_reloaded(monkeypatch):
    # Reproduce the screenshot: existing imported Settings has no ECOS property.
    monkeypatch.delattr(config.Settings,'ecos_fingerprint')
    monkeypatch.delitem(config.FIELDS,'ecos')
    def unavailable(*a):raise APIError('test unavailable')
    monkeypatch.setattr(KRX,'latest',unavailable)
    monkeypatch.setattr(KIS,'quote',unavailable)
    at=app(monkeypatch)
    assert not at.exception
    assert hasattr(config.Settings,'ecos_fingerprint')
    assert config.read_settings({'ecos':{'api_key':'test'}}).ecos=='test'
    login(at)
    at.sidebar.radio[0].set_value('거시경제 · 시장환경').run()
    assert not at.exception
    assert any('[ecos]' in x.value for x in at.info)
