import pytest


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        username="alice", email="alice@example.org", sub="cognito-sub-alice"
    )
