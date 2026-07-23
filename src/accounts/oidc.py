"""OIDC backend for Cognito (and, with endpoint overrides, Entra).

The backend maps the IdP identity onto the local User's `sub`/`identity_provider`
fields. It carries NO authorization — group membership from the IdP is only ever
used as a coarse login gate (OIDC_REQUIRED_GROUP), never as permissions. All
authorization lives in OpenFGA. See docs/004-identity-and-tokens.md.
"""

from django.conf import settings
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class CognitoOIDCBackend(OIDCAuthenticationBackend):
    def get_username(self, claims):
        return (
            claims.get("cognito:username")
            or claims.get("preferred_username")
            or claims.get("email")
            or super().get_username(claims)
        )

    def get_userinfo(self, access_token, id_token, payload):
        # cognito:groups / cognito:username live in the ID token, not userinfo.
        userinfo = super().get_userinfo(access_token, id_token, payload)
        userinfo.setdefault("cognito:groups", payload.get("cognito:groups", []))
        userinfo.setdefault("cognito:username", payload.get("cognito:username", ""))
        return userinfo

    def verify_claims(self, claims):
        required_group = getattr(settings, "OIDC_REQUIRED_GROUP", "")
        if required_group:
            groups = claims.get("cognito:groups", []) or claims.get("groups", [])
            if required_group not in groups:
                return False
        return super().verify_claims(claims)

    def filter_users_by_claims(self, claims):
        sub = claims.get("sub")
        if sub:
            users = self.UserModel.objects.filter(sub=sub)
            if users.exists():
                return users
        return super().filter_users_by_claims(claims)

    def create_user(self, claims):
        user = super().create_user(claims)
        user.sub = claims.get("sub") or None
        user.identity_provider = getattr(settings, "OIDC_PROVIDER_NAME", "cognito")
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
        user.set_unusable_password()
        user.save(update_fields=["sub", "identity_provider", "first_name", "last_name"])
        return user
