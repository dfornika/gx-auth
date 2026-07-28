import hashlib
import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Platform user.

    `sub` is the OIDC subject claim from the IdP (Cognito/Entra) and is the
    stable identity used to build the OpenFGA subject id (`user:<sub>`).
    See docs/004-identity-and-tokens.md.
    """

    sub = models.CharField(max_length=255, unique=True, null=True, blank=True)
    identity_provider = models.CharField(max_length=64, blank=True, default="")

    @property
    def fga_subject(self) -> str | None:
        """The OpenFGA subject id for this user, or None if it has none.

        Only the IdP `sub` is a globally stable identity. The store is shared
        across services, so a locally-minted id is not merely unportable — it
        *collides*: this row's pk 3 and some consumer's pk 3 would both be
        `user:3` and would grant each other's access. An account with no `sub`
        therefore has no subject at all, and callers must deny.

        Returning None rather than raising keeps the denial the caller's
        decision (a superuser short-circuit is a legitimate answer), but it must
        be an explicit one — never interpolate this into an id unchecked.
        See docs/004-identity-and-tokens.md.
        """
        return f"user:{self.sub}" if self.sub else None


class APIKey(models.Model):
    """Long-lived, user-scoped API key for the control-plane API.

    Mirrors gx-core's pattern: a random token shown once; only its hash is
    stored. The 8-char prefix indexes the lookup. The key identifies the user;
    OpenFGA still makes every authorization decision.
    """

    PREFIX_LEN = 8

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=255)
    prefix = models.CharField(max_length=PREFIX_LEN, db_index=True)
    hashed_key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix}…)"

    @staticmethod
    def _hash(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()

    @classmethod
    def generate(cls, user: User, name: str) -> tuple["APIKey", str]:
        raw_key = secrets.token_urlsafe(32)
        api_key = cls.objects.create(
            user=user,
            name=name,
            prefix=raw_key[: cls.PREFIX_LEN],
            hashed_key=cls._hash(raw_key),
        )
        return api_key, raw_key

    def verify(self, raw_key: str) -> bool:
        return not self.revoked and secrets.compare_digest(self.hashed_key, self._hash(raw_key))

    def touch(self) -> None:
        APIKey.objects.filter(pk=self.pk).update(last_used_at=timezone.now())
