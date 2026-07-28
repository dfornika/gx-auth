"""Tests for the control-plane client (audited grants over HTTP)."""

from unittest.mock import patch

import httpx
import pytest
from gx_auth_sdk import grant, revoke

_FAKE_REQUEST = httpx.Request("POST", "http://test")


@pytest.fixture
def mock_httpx(sdk_config):
    """Mock httpx.request to capture calls without hitting the network."""
    with patch("gx_auth_sdk.control_plane.httpx.request") as mock:
        mock.return_value = httpx.Response(200, request=_FAKE_REQUEST)
        yield mock


class TestGrant:
    def test_posts_to_grants_endpoint(self, mock_httpx):
        grant("user:alice", "member", "project:1", reason="onboarding")
        mock_httpx.assert_called_once()
        args, kwargs = mock_httpx.call_args
        assert args == ("POST", "http://gxauth-test:8000/api/authz/grants")
        assert kwargs["json"] == {
            "subject": "user:alice",
            "relation": "member",
            "object": "project:1",
            "reason": "onboarding",
        }

    def test_sends_bearer_token(self, mock_httpx):
        grant("user:alice", "member", "project:1")
        _, kwargs = mock_httpx.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"

    def test_rejects_malformed_subject(self, mock_httpx):
        with pytest.raises(ValueError, match="empty id"):
            grant("user:", "member", "project:1")
        mock_httpx.assert_not_called()

    def test_rejects_malformed_object(self, mock_httpx):
        with pytest.raises(ValueError, match="empty id"):
            grant("user:alice", "member", "project:")
        mock_httpx.assert_not_called()

    def test_raises_on_http_error(self, mock_httpx):
        mock_httpx.return_value = httpx.Response(403, request=_FAKE_REQUEST)
        with pytest.raises(httpx.HTTPStatusError):
            grant("user:alice", "member", "project:1")


class TestRevoke:
    def test_deletes_from_grants_endpoint(self, mock_httpx):
        revoke("user:alice", "member", "project:1", reason="offboarding")
        mock_httpx.assert_called_once()
        args, kwargs = mock_httpx.call_args
        assert args == ("DELETE", "http://gxauth-test:8000/api/authz/grants")
        assert kwargs["json"]["subject"] == "user:alice"

    def test_rejects_malformed_subject(self, mock_httpx):
        with pytest.raises(ValueError):
            revoke("user:", "member", "project:1")
        mock_httpx.assert_not_called()
