"""Tests for SDK configuration resolution."""

import gx_auth_sdk.config as config_mod
import pytest
from gx_auth_sdk.config import Config, configure, get_config


@pytest.fixture(autouse=True)
def _reset_config():
    """Reset the module-level singleton between tests."""
    config_mod._config = None
    yield
    config_mod._config = None


class TestConfigure:
    def test_explicit_values(self):
        cfg = configure(
            fga_api_url="http://fga:8080",
            fga_store_id="store-1",
            control_plane_url="http://gxauth:8000",
            control_plane_api_key="key-1",
        )
        assert cfg == Config(
            fga_api_url="http://fga:8080",
            fga_store_id="store-1",
            control_plane_url="http://gxauth:8000",
            control_plane_api_key="key-1",
        )

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("FGA_API_URL", "http://env-fga:9090")
        monkeypatch.setenv("FGA_STORE_ID", "env-store")
        monkeypatch.setenv("GXAUTH_URL", "http://env-gxauth:9000")
        monkeypatch.setenv("GXAUTH_API_KEY", "env-key")
        cfg = configure()
        assert cfg.fga_api_url == "http://env-fga:9090"
        assert cfg.fga_store_id == "env-store"
        assert cfg.control_plane_url == "http://env-gxauth:9000"
        assert cfg.control_plane_api_key == "env-key"

    def test_defaults_for_optional_fields(self, monkeypatch):
        monkeypatch.setenv("FGA_STORE_ID", "store-1")
        monkeypatch.delenv("FGA_API_URL", raising=False)
        monkeypatch.delenv("GXAUTH_URL", raising=False)
        monkeypatch.delenv("GXAUTH_API_KEY", raising=False)
        cfg = configure()
        assert cfg.fga_api_url == "http://localhost:8080"
        assert cfg.control_plane_url == "http://localhost:8000"
        assert cfg.control_plane_api_key == ""

    def test_missing_store_id_raises(self, monkeypatch):
        monkeypatch.delenv("FGA_STORE_ID", raising=False)
        with pytest.raises(RuntimeError, match="FGA_STORE_ID"):
            configure()

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("FGA_STORE_ID", "env-store")
        monkeypatch.setenv("FGA_API_URL", "http://env-fga:9090")
        cfg = configure(fga_api_url="http://explicit:8080", fga_store_id="explicit-store")
        assert cfg.fga_api_url == "http://explicit:8080"
        assert cfg.fga_store_id == "explicit-store"


class TestGetConfig:
    def test_lazy_init_from_env(self, monkeypatch):
        monkeypatch.setenv("FGA_STORE_ID", "lazy-store")
        cfg = get_config()
        assert cfg.fga_store_id == "lazy-store"

    def test_returns_existing_config(self, monkeypatch):
        monkeypatch.setenv("FGA_STORE_ID", "store-1")
        first = configure(fga_store_id="first")
        second = get_config()
        assert first is second
