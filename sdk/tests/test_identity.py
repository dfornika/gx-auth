"""Tests for CognitoJWTAuth and StubHeaderAuth.

Uses a locally-generated RSA key pair to produce real JWTs — no network calls,
no Cognito dependency. The JWKS client is patched to return the local public key.

Django setup is handled by conftest.py (must run before ninja-dependent imports).
"""

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from gx_auth_sdk.identity import CognitoJWTAuth, StubHeaderAuth
from jwt import PyJWK

REGION = "ca-central-1"
POOL_ID = "ca-central-1_TestPool"
CLIENT_ID = "test-client-id"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"

# --- RSA key pair for signing test JWTs ---

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_private_pem = _private_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
_public_key = _private_key.public_key()
_public_pem = _public_key.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)
_public_jwk = PyJWK.from_json(
    json.dumps(
        pyjwt.algorithms.RSAAlgorithm.to_jwk(_public_key, as_dict=True)
        | {"kid": "test-kid", "use": "sig", "alg": "RS256"}
    )
)


def _make_token(claims: dict | None = None, **overrides) -> str:
    payload = {
        "sub": "cognito-sub-alice",
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "token_use": "id",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "email": "alice@example.org",
    }
    if claims:
        payload.update(claims)
    payload.update(overrides)
    return pyjwt.encode(
        payload, _private_pem, algorithm="RS256", headers={"kid": "test-kid"}
    )


@pytest.fixture
def auth():
    """A CognitoJWTAuth whose JWKS client returns our local key."""
    a = CognitoJWTAuth(region=REGION, user_pool_id=POOL_ID, client_id=CLIENT_ID)
    mock_jwks = MagicMock()
    mock_jwks.get_signing_key_from_jwt.return_value = _public_jwk
    a._jwks_client = mock_jwks
    return a


@pytest.fixture
def request_obj():
    return SimpleNamespace()


# --- CognitoJWTAuth ---------------------------------------------------------


class TestCognitoJWTAuth:
    def test_valid_id_token_returns_subject(self, auth, request_obj):
        token = _make_token()
        result = auth.authenticate(request_obj, token)
        assert result == "user:cognito-sub-alice"

    def test_different_sub(self, auth, request_obj):
        token = _make_token(sub="cognito-sub-bob")
        result = auth.authenticate(request_obj, token)
        assert result == "user:cognito-sub-bob"

    def test_rejects_access_token(self, auth, request_obj):
        token = _make_token(token_use="access")
        result = auth.authenticate(request_obj, token)
        assert result is None

    def test_rejects_missing_sub(self, auth, request_obj):
        token = _make_token(sub="")
        result = auth.authenticate(request_obj, token)
        assert result is None

    def test_rejects_wrong_issuer(self, auth, request_obj):
        token = _make_token(iss="https://evil.example.com")
        result = auth.authenticate(request_obj, token)
        assert result is None

    def test_rejects_wrong_audience(self, auth, request_obj):
        token = _make_token(aud="wrong-client-id")
        result = auth.authenticate(request_obj, token)
        assert result is None

    def test_rejects_expired_token(self, auth, request_obj):
        token = _make_token(exp=int(time.time()) - 3600)
        result = auth.authenticate(request_obj, token)
        assert result is None

    def test_rejects_garbage_token(self, auth, request_obj):
        auth._jwks_client.get_signing_key_from_jwt.side_effect = (
            pyjwt.exceptions.DecodeError("not a jwt")
        )
        result = auth.authenticate(request_obj, "not.a.jwt")
        assert result is None

    def test_rejects_tampered_signature(self, auth, request_obj):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        token = pyjwt.encode(
            {
                "sub": "cognito-sub-eve",
                "iss": ISSUER,
                "aud": CLIENT_ID,
                "token_use": "id",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
            },
            other_pem,
            algorithm="RS256",
            headers={"kid": "test-kid"},
        )
        result = auth.authenticate(request_obj, token)
        assert result is None

    def test_skips_audience_check_when_no_client_id(self, request_obj):
        a = CognitoJWTAuth(region=REGION, user_pool_id=POOL_ID, client_id="")
        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = _public_jwk
        a._jwks_client = mock_jwks
        token = _make_token(aud="any-client-id")
        result = a.authenticate(request_obj, token)
        assert result == "user:cognito-sub-alice"


class TestCognitoJWTAuthConfig:
    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_Pool")
        monkeypatch.setenv("COGNITO_CLIENT_ID", "env-client")
        a = CognitoJWTAuth()
        assert a._region == "us-east-1"
        assert a._user_pool_id == "us-east-1_Pool"
        assert a._client_id == "env-client"
        assert a._issuer == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Pool"

    def test_constructor_overrides_env(self, monkeypatch):
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_Pool")
        a = CognitoJWTAuth(region="eu-west-1", user_pool_id="eu-west-1_Other")
        assert a._region == "eu-west-1"

    def test_missing_config_raises(self, monkeypatch):
        monkeypatch.delenv("COGNITO_REGION", raising=False)
        monkeypatch.delenv("COGNITO_USER_POOL_ID", raising=False)
        with pytest.raises(RuntimeError, match="COGNITO_REGION"):
            CognitoJWTAuth()


# --- StubHeaderAuth ---------------------------------------------------------


class TestStubHeaderAuth:
    def test_returns_subject(self, request_obj):
        stub = StubHeaderAuth()
        result = stub.authenticate(request_obj, "alice")
        assert result == "user:alice"

    def test_returns_none_for_empty_key(self, request_obj):
        stub = StubHeaderAuth()
        assert stub.authenticate(request_obj, "") is None
