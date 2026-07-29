"""Identity extraction for django-ninja. Requires the `ninja` extra.

Ships two authenticators:

- ``CognitoJWTAuth``: production — validates a Cognito ID token JWT against
  the pool's JWKS, extracts ``sub``, and returns ``user:<sub>`` as
  ``request.auth``. Configure via env vars or constructor kwargs.
- ``StubHeaderAuth``: dev-only — trusts an unauthenticated header.

See gx-auth/docs/004-identity-and-tokens.md.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import jwt
from jwt import PyJWKClient
from ninja.security import APIKeyHeader, HttpBearer

logger = logging.getLogger("gx_auth_sdk.identity")


class CognitoJWTAuth(HttpBearer):
    """Validate a Cognito ID token and return ``user:<sub>``.

    Usage in a consumer's ``api.py``::

        from gx_auth_sdk import CognitoJWTAuth

        auth = CognitoJWTAuth()          # reads env vars
        api = NinjaAPI(auth=auth)

    Or with explicit config::

        auth = CognitoJWTAuth(
            region="ca-central-1",
            user_pool_id="ca-central-1_NhqDhcnKG",
            client_id="...",
        )

    The token must be an **ID token** (``token_use: id``). Access tokens are
    rejected — authorization lives in OpenFGA, not in token scopes (ADR 0002).
    """

    def __init__(
        self,
        *,
        region: str | None = None,
        user_pool_id: str | None = None,
        client_id: str | None = None,
    ):
        super().__init__()
        self._region = region or os.environ.get("COGNITO_REGION", "")
        self._user_pool_id = user_pool_id or os.environ.get("COGNITO_USER_POOL_ID", "")
        self._client_id = client_id or os.environ.get("COGNITO_CLIENT_ID", "")

        if not self._region or not self._user_pool_id:
            raise RuntimeError(
                "CognitoJWTAuth requires region + user_pool_id. "
                "Set COGNITO_REGION and COGNITO_USER_POOL_ID env vars, "
                "or pass them to the constructor."
            )

        self._issuer = (
            f"https://cognito-idp.{self._region}.amazonaws.com/{self._user_pool_id}"
        )
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._jwks_client: PyJWKClient | None = None
        self._jwks_lock = threading.Lock()

    @property
    def _jwks(self) -> PyJWKClient:
        if self._jwks_client is None:
            with self._jwks_lock:
                if self._jwks_client is None:
                    self._jwks_client = PyJWKClient(
                        self._jwks_url, cache_keys=True, lifespan=3600
                    )
        return self._jwks_client

    def authenticate(self, request: Any, token: str) -> str | None:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
        except (jwt.exceptions.PyJWKClientError, jwt.exceptions.DecodeError) as exc:
            logger.debug("JWKS lookup failed: %s", exc)
            return None

        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "issuer": self._issuer,
        }
        if self._client_id:
            decode_kwargs["audience"] = self._client_id
        else:
            decode_kwargs["options"] = {"verify_aud": False}

        try:
            claims = jwt.decode(token, signing_key.key, **decode_kwargs)
        except jwt.InvalidTokenError as exc:
            logger.debug("JWT validation failed: %s", exc)
            return None

        if claims.get("token_use") != "id":
            logger.debug(
                "Rejected token: token_use=%r (expected 'id')",
                claims.get("token_use"),
            )
            return None

        sub = claims.get("sub")
        if not sub:
            logger.debug("Rejected token: missing sub claim")
            return None

        return f"user:{sub}"


class StubHeaderAuth(APIKeyHeader):
    """Dev-only identity: `X-User-Id: alice` -> subject `user:alice`.

    NOT for production — it trusts an unauthenticated header. Swap for a real
    OIDC JWT authenticator before any non-local use.
    """

    param_name = "X-User-Id"

    def authenticate(self, request, key):
        return f"user:{key}" if key else None
