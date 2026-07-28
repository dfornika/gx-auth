import pytest

from accounts.models import APIKey


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
    assert str(superuser.pk) not in str(superuser.fga_subject)
