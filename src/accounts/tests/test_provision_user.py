import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User


def provision(username, **opts):
    out = io.StringIO()
    call_command("provision_user", username, stdout=out, stderr=io.StringIO(), **opts)
    return out.getvalue().strip()


@pytest.mark.django_db
def test_creates_user_with_sub():
    result = provision("jane", sub="cognito-sub-jane", email="jane@example.org")
    user = User.objects.get(username="jane")
    assert user.sub == "cognito-sub-jane"
    assert user.email == "jane@example.org"
    assert user.identity_provider == "cognito"
    assert result == "user:cognito-sub-jane"


@pytest.mark.django_db
def test_prints_fga_subject():
    result = provision("jane", sub="cognito-sub-jane")
    assert result == "user:cognito-sub-jane"


@pytest.mark.django_db
def test_requires_sub():
    with pytest.raises(CommandError, match="--sub"):
        provision("jane")


@pytest.mark.django_db
def test_rejects_blank_sub():
    with pytest.raises(CommandError, match="must not be blank"):
        provision("jane", sub="   ")


@pytest.mark.django_db
def test_rejects_duplicate_sub(user):
    with pytest.raises(CommandError, match="already belongs to user"):
        provision("impostor", sub=user.sub)


@pytest.mark.django_db
def test_backfills_sub_on_existing_user(superuser):
    result = provision(superuser.username, sub="idp-sub-root")
    superuser.refresh_from_db()
    assert superuser.sub == "idp-sub-root"
    assert superuser.fga_subject == "user:idp-sub-root"
    assert result == "user:idp-sub-root"


@pytest.mark.django_db
def test_backfill_rejects_duplicate_sub(user, superuser):
    with pytest.raises(CommandError, match="already belongs to user"):
        provision(superuser.username, sub=user.sub)
    superuser.refresh_from_db()
    assert superuser.sub is None


@pytest.mark.django_db
def test_backfill_preserves_existing_identity_provider(db, django_user_model):
    u = django_user_model.objects.create_user(username="entra-user", identity_provider="entra")
    provision(u.username, sub="entra-sub-123")
    u.refresh_from_db()
    assert u.sub == "entra-sub-123"
    assert u.identity_provider == "entra"


@pytest.mark.django_db
def test_refuses_to_repoint_an_existing_sub(user):
    with pytest.raises(CommandError, match="Refusing to repoint"):
        provision(user.username, sub="different-sub")
    user.refresh_from_db()
    assert user.sub == "cognito-sub-alice"


@pytest.mark.django_db
def test_noop_when_sub_already_matches(user):
    result = provision(user.username, sub=user.sub)
    assert result == f"user:{user.sub}"


@pytest.mark.django_db
def test_custom_identity_provider():
    provision("entra-svc", sub="entra-sub-svc", identity_provider="entra")
    user = User.objects.get(username="entra-svc")
    assert user.identity_provider == "entra"
