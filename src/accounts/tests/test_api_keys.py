import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import APIKey, User


def mint(username, **opts):
    """Run create_api_key, returning the raw key it prints on stdout."""
    out = io.StringIO()
    call_command("create_api_key", username, stdout=out, stderr=io.StringIO(), **opts)
    return out.getvalue().strip()


@pytest.mark.django_db
def test_generate_returns_raw_key_once_and_stores_only_hash(user):
    api_key, raw_key = APIKey.generate(user=user, name="cli")
    assert raw_key
    assert api_key.hashed_key != raw_key
    assert api_key.prefix == raw_key[: APIKey.PREFIX_LEN]


@pytest.mark.django_db
def test_verify_accepts_correct_key_and_rejects_wrong(user):
    api_key, raw_key = APIKey.generate(user=user, name="cli")
    assert api_key.verify(raw_key) is True
    assert api_key.verify("not-the-key") is False


@pytest.mark.django_db
def test_revoked_key_does_not_verify(user):
    api_key, raw_key = APIKey.generate(user=user, name="cli")
    api_key.revoked = True
    assert api_key.verify(raw_key) is False


@pytest.mark.django_db
def test_fga_subject_uses_sub(user):
    assert user.fga_subject == "user:cognito-sub-alice"


@pytest.mark.django_db
def test_fga_subject_is_none_without_a_sub(superuser):
    """An account that never came from the IdP has no subject — not a local one.

    The pk fallback this replaces was actively unsafe: the store is shared, so
    `user:<pk>` collides with an unrelated consumer's row of the same pk.
    """
    assert superuser.sub is None
    assert superuser.fga_subject is None


# --- create_api_key: every key's user must carry an IdP sub (ADR 0003) ------


@pytest.mark.django_db
def test_create_api_key_creates_user_with_the_given_sub():
    raw_key = mint("svc-catalog", sub="idp-sub-catalog", identity_provider="cognito")
    user = User.objects.get(username="svc-catalog")
    assert user.sub == "idp-sub-catalog"
    assert user.identity_provider == "cognito"
    assert user.fga_subject == "user:idp-sub-catalog"
    assert user.api_keys.get().verify(raw_key)


@pytest.mark.django_db
def test_create_api_key_refuses_to_invent_a_sub():
    """The old behaviour minted `svc-<username>`, which collides across services."""
    with pytest.raises(CommandError, match="--sub was not given"):
        mint("svc-catalog")
    assert not User.objects.filter(username="svc-catalog").exists()


@pytest.mark.django_db
def test_create_api_key_rejects_a_sub_already_in_use(user):
    with pytest.raises(CommandError, match="already belongs to user 'alice'"):
        mint("svc-impostor", sub=user.sub)


@pytest.mark.django_db
def test_create_api_key_backfills_a_blank_sub(superuser):
    mint(superuser.username, sub="idp-sub-root")
    superuser.refresh_from_db()
    assert superuser.fga_subject == "user:idp-sub-root"


@pytest.mark.django_db
def test_create_api_key_backfill_rejects_a_sub_already_in_use(user, superuser):
    """Same uniqueness check as the new-user branch, for the backfill path."""
    with pytest.raises(CommandError, match="already belongs to user 'alice'"):
        mint(superuser.username, sub=user.sub)
    superuser.refresh_from_db()
    assert superuser.sub is None


@pytest.mark.django_db
def test_create_api_key_backfill_preserves_existing_identity_provider(db, django_user_model):
    """Don't overwrite identity_provider with the argparse default on backfill."""
    u = django_user_model.objects.create_user(
        username="entra-user", identity_provider="entra"
    )
    assert not u.sub
    mint(u.username, sub="entra-sub-123")
    u.refresh_from_db()
    assert u.sub == "entra-sub-123"
    assert u.identity_provider == "entra"


@pytest.mark.django_db
def test_create_api_key_refuses_to_repoint_an_existing_sub(user):
    """Tuples already written against the old subject would silently stop applying."""
    with pytest.raises(CommandError, match="Refusing to repoint"):
        mint(user.username, sub="some-other-sub")
    user.refresh_from_db()
    assert user.sub == "cognito-sub-alice"


@pytest.mark.django_db
def test_create_api_key_reuses_an_existing_user_without_a_sub_argument(user):
    raw_key = mint(user.username, name="cli")
    assert user.api_keys.get(name="cli").verify(raw_key)
