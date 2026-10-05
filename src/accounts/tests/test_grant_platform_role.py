import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from authz.models import GrantAudit


def run(*args):
    out = io.StringIO()
    call_command("grant_platform_role", *args, stdout=out)
    return out.getvalue().strip()


@pytest.mark.django_db
def test_grants_platform_admin_and_audits(fake_fga):
    assert run("admin", "sub-olga", "--reason", "on-call") == (
        "grant user:sub-olga admin platform:gx"
    )
    assert fake_fga.writes == [("user:sub-olga", "admin", "platform:gx")]
    audit = GrantAudit.objects.get()
    assert (audit.action, audit.subject, audit.object) == ("grant", "user:sub-olga", "platform:gx")
    assert audit.performed_by is None
    assert audit.reason == "on-call"
    assert audit.status == GrantAudit.Status.APPLIED


@pytest.mark.django_db
def test_revokes_delegate(fake_fga):
    run("delegate", "svc-client", "--revoke")
    assert fake_fga.deletes == [("user:svc-client", "delegate", "platform:gx")]
    assert GrantAudit.objects.get().action == "revoke"


@pytest.mark.django_db
def test_uses_configured_platform_id(fake_fga, settings):
    settings.GXAUTH_PLATFORM_ID = "staging"
    run("admin", "sub-olga")
    assert fake_fga.writes == [("user:sub-olga", "admin", "platform:staging")]


@pytest.mark.django_db
@pytest.mark.parametrize("sub", ["", "user:sub-olga", "has space"])
def test_rejects_anything_but_a_bare_sub(fake_fga, sub):
    with pytest.raises(CommandError, match="bare IdP sub"):
        run("admin", sub)
    assert fake_fga.writes == []
    assert not GrantAudit.objects.exists()


@pytest.mark.django_db
def test_failed_engine_write_is_recorded_as_failed(fake_fga):
    fake_fga.fail_writes = True
    with pytest.raises(Exception, match="simulated engine write failure"):
        run("admin", "sub-olga")
    assert GrantAudit.objects.get().status == GrantAudit.Status.FAILED
