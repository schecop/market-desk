import pytest

from market_desk.config import Settings, get_settings


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "fake_url")
    settings = Settings()
    assert settings.database_url == "fake_url"


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    settings_call1 = get_settings()
    settings_call2 = get_settings()

    assert settings_call1 is settings_call2
    monkeypatch.setenv("DATABASE_URL", "fake_url")
    settings_call3 = get_settings()

    assert settings_call1.database_url == settings_call3.database_url
    get_settings.cache_clear()
    settings_call3 = get_settings()

    assert settings_call3.database_url == "fake_url"

    get_settings.cache_clear()
