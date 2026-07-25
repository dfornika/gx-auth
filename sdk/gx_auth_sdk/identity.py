"""Identity extraction for django-ninja. Requires the `ninja` extra.

For now this ships a dev-only stub. A real Cognito/Entra JWT authenticator
(verify against JWKS, map `sub` -> `user:<sub>`) belongs here later — see
gx-auth/docs/004-identity-and-tokens.md.
"""

from __future__ import annotations

from ninja.security import APIKeyHeader


class StubHeaderAuth(APIKeyHeader):
    """Dev-only identity: `X-User-Id: alice` -> subject `user:alice`.

    NOT for production — it trusts an unauthenticated header. Swap for a real
    OIDC JWT authenticator before any non-local use.
    """

    param_name = "X-User-Id"

    def authenticate(self, request, key):
        return f"user:{key}" if key else None
