import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from authz.models import GrantAudit

OLD = timezone.now() - timedelta(hours=1)
TUPLE = ("user:bob", "member", "project:demo")


def run(*args):
    out = io.StringIO()
    call_command("reconcile_grant_audit", *args, stdout=out)
    return out.getvalue()


def pending(action, *, at=OLD, tuple_=TUPLE):
    audit = GrantAudit.objects.create(
        action=action, subject=tuple_[0], relation=tuple_[1], object=tuple_[2]
    )
    GrantAudit.objects.filter(pk=audit.pk).update(created_at=at)  # auto_now_add
    return audit


def status(audit):
    audit.refresh_from_db()
    return audit.status


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action, in_store, expected",
    [
        ("grant", True, "applied"),
        ("grant", False, "failed"),
        ("revoke", False, "applied"),
        ("revoke", True, "failed"),
    ],
)
def test_settles_pending_rows_from_the_store(fake_fga, action, in_store, expected):
    fake_fga.tuples = [TUPLE] if in_store else []
    audit = pending(action)

    out = run()

    assert status(audit) == expected
    assert "settled 1; 0 superseded" in out


@pytest.mark.django_db
def test_leaves_recent_rows_alone(fake_fga):
    """A just-created pending row may be a request still in flight."""
    audit = pending("grant", at=timezone.now())
    run()
    assert status(audit) == "pending"
    assert not [c for c in fake_fga.calls if c[0] == "read"]


@pytest.mark.django_db
def test_superseded_rows_are_reported_not_guessed(fake_fga):
    fake_fga.tuples = []
    earlier = pending("grant", at=OLD - timedelta(minutes=5))
    later = pending("revoke")
    GrantAudit.objects.filter(pk=later.pk).update(status="applied")

    out = run()

    assert status(earlier) == "pending"
    assert "superseded" in out and "review by hand" in out


@pytest.mark.django_db
def test_dry_run_changes_nothing(fake_fga):
    fake_fga.tuples = [TUPLE]
    audit = pending("grant")

    out = run("--dry-run")

    assert status(audit) == "pending"
    assert "would settle 1" in out


@pytest.mark.django_db
def test_ignores_settled_rows(fake_fga):
    audit = pending("grant")
    GrantAudit.objects.filter(pk=audit.pk).update(status="failed")
    assert "settled 0" in run()
