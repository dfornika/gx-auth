"""Shared fixtures for SDK tests."""

from unittest.mock import MagicMock

import gx_auth_sdk.config as config_mod
import pytest
from gx_auth_sdk.config import Config
from openfga_sdk import CheckResponse, ListObjectsResponse


@pytest.fixture
def sdk_config(monkeypatch):
    """Install a test config so SDK calls don't need real env vars."""
    cfg = Config(
        fga_api_url="http://fga-test:8080",
        fga_store_id="test-store",
        control_plane_url="http://gxauth-test:8000",
        control_plane_api_key="test-key",
    )
    monkeypatch.setattr(config_mod, "_config", cfg)
    return cfg


class FakeOpenFgaClient:
    """Minimal stand-in for openfga_sdk.sync.OpenFgaClient."""

    def __init__(self):
        self.check_response = CheckResponse(allowed=False)
        self.list_objects_response = ListObjectsResponse(objects=[])
        self.writes: list = []
        self.deletes: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def check(self, body):
        self._last_check = body
        return self.check_response

    def list_objects(self, body):
        self._last_list_objects = body
        return self.list_objects_response

    def write(self, body):
        if body.writes:
            self.writes.extend(body.writes)
        if body.deletes:
            self.deletes.extend(body.deletes)
        return MagicMock()


@pytest.fixture
def fake_fga(monkeypatch, sdk_config):
    """Patch the SDK's _client() to return a fake OpenFGA client."""
    fake = FakeOpenFgaClient()
    monkeypatch.setattr("gx_auth_sdk.client._client", lambda: fake)
    return fake
