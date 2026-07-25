"""Access control and degraded-state behaviour for the inspector pages.

Rendered markup is deliberately barely asserted — it would be brittle against
django-unfold upgrades.
"""

import pytest
from django.urls import reverse

URLS = ["fga_inspector:tuples", "fga_inspector:expand", "fga_inspector:tree"]


@pytest.mark.parametrize("name", URLS)
def test_anonymous_is_redirected_to_the_admin_login(client, name, db):
    response = client.get(reverse(name))

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.parametrize("name", URLS)
def test_staff_without_superuser_is_forbidden(client, django_user_model, name, db):
    staff = django_user_model.objects.create_user(username="staffer", password="pw", is_staff=True)
    client.force_login(staff)

    # The whole authorization graph is more than GrantAudit exposes.
    assert client.get(reverse(name)).status_code == 403


@pytest.mark.parametrize("name", URLS)
def test_superuser_gets_the_page(client, superuser, fake_fga, name):
    client.force_login(superuser)

    assert client.get(reverse(name)).status_code == 200


def test_unconfigured_store_renders_guidance_without_calling_the_engine(
    client, superuser, fake_fga, settings
):
    settings.FGA_STORE_ID = ""
    client.force_login(superuser)

    response = client.get(reverse("fga_inspector:tuples"))

    assert response.status_code == 200
    assert b"No OpenFGA store is configured" in response.content
    assert fake_fga.calls == []


def test_engine_failure_is_reported_not_raised(client, superuser, fake_fga, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("authz.services.fga.read_model", boom)
    client.force_login(superuser)

    response = client.get(reverse("fga_inspector:tuples"))

    assert response.status_code == 200
    assert b"Engine unavailable" in response.content


def test_stale_model_pin_is_flagged(client, superuser, fake_fga, settings):
    """The condition this repo was actually found in: FGA_MODEL_ID pinned to a
    model the store has since superseded, so checks answer against the old one."""
    from conftest import build_model

    old, new = "01OLDMODEL00000000000000000", "01NEWMODEL00000000000000000"
    settings.FGA_MODEL_ID = old
    fake_fga.model = build_model(old)
    fake_fga.latest_model = build_model(new)
    client.force_login(superuser)

    response = client.get(reverse("fga_inspector:tree")).content.decode()

    assert "pinned model is not the newest" in response
    assert new in response


def test_tuple_browser_lists_seed_tuples(client, superuser, fake_fga):
    client.force_login(superuser)

    body = client.get(reverse("fga_inspector:tuples")).content.decode()

    assert "user:alice" in body
    assert "project:demo-sub" in body


def test_scan_banner_appears_for_unsupported_filters(client, superuser, fake_fga):
    client.force_login(superuser)

    body = client.get(reverse("fga_inspector:tuples"), {"relation": "admin"}).content.decode()

    assert "cannot filter on this combination" in body
    assert "Scanned" in body


def test_grant_audit_changelist_links_to_the_inspector(client, superuser, fake_fga):
    client.force_login(superuser)

    body = client.get(reverse("admin:authz_grantaudit_changelist")).content.decode()

    for name in URLS:
        assert reverse(name) in body
