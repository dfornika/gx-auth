"""Control-plane authorization tests, through the real endpoints.

The engine is faked (`fake_fga`): it answers `check` from an explicit allow-set
and records writes, so these tests pin down *which questions* gx-auth asks and
what it does with the answers. Whether the model answers them correctly is the
job of `fga/model.tests.yaml`.
"""

import json

import pytest

from accounts.models import APIKey
from authz.models import GrantAudit
from authz.services import fga

ALICE = "user:cognito-sub-alice"  # the `user` fixture's subject
SERVICE = "user:svc-sds-client"
PLATFORM = "platform:gx"
PLATFORM_EDGE = ((PLATFORM, "platform", "project:1"),)


@pytest.fixture
def api(client, user, fake_fga):
    """Call the API as `user` (alice) with a real API key."""
    return _caller(client, user)


@pytest.fixture
def service_user(db, django_user_model):
    return django_user_model.objects.create_user(username="svc-sds", sub="svc-sds-client")


def _caller(client, principal):
    _, raw = APIKey.generate(user=principal, name="test")

    def call(method, path, body):
        return getattr(client, method)(
            f"/api/authz/{path}",
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw}",
        )

    return call


def _grant(**overrides):
    body = {"subject": "user:bob", "relation": "member", "object": "project:1"}
    return {**body, **overrides}


def _checks(fake):
    return [c[1:] for c in fake.calls if c[0] == "check"]


# --- grants: who may -------------------------------------------------------


@pytest.mark.django_db
def test_project_admin_can_grant(api, fake_fga, user):
    fake_fga.allowed.add((ALICE, "can_administer", "project:1"))

    resp = api("post", "grants", _grant(reason="joined the lab"))

    assert resp.status_code == 201
    assert fake_fga.writes == [("user:bob", "member", "project:1")]
    audit = GrantAudit.objects.get()
    assert (audit.action, audit.subject, audit.relation, audit.object) == (
        "grant",
        "user:bob",
        "member",
        "project:1",
    )
    assert audit.performed_by == user
    assert audit.on_behalf_of == ""
    assert audit.reason == "joined the lab"


@pytest.mark.django_db
def test_grant_check_supplies_the_platform_edge_contextually(api, fake_fga):
    """The platform edge is what lets platform admins manage any project; it is
    asserted per-check rather than stored (see policy.can_manage_grants)."""
    fake_fga.allowed.add((ALICE, "can_administer", "project:1"))

    api("post", "grants", _grant())

    assert _checks(fake_fga) == [(ALICE, "can_administer", "project:1", PLATFORM_EDGE)]


@pytest.mark.django_db
def test_non_admin_cannot_grant(api, fake_fga):
    resp = api("post", "grants", _grant(relation="admin"))

    assert resp.status_code == 403
    assert "can_administer" in resp.json()["detail"]
    assert fake_fga.writes == []
    assert not GrantAudit.objects.exists()


@pytest.mark.django_db
def test_non_admin_cannot_revoke(api, fake_fga):
    resp = api("delete", "grants", _grant())

    assert resp.status_code == 403
    assert fake_fga.deletes == []
    assert not GrantAudit.objects.exists()


@pytest.mark.django_db
def test_project_admin_can_revoke(api, fake_fga):
    fake_fga.allowed.add((ALICE, "can_administer", "project:1"))

    resp = api("delete", "grants", _grant())

    assert resp.status_code == 204
    assert fake_fga.deletes == [("user:bob", "member", "project:1")]
    assert GrantAudit.objects.get().action == GrantAudit.Action.REVOKE


@pytest.mark.django_db
def test_caller_without_sub_is_denied(client, fake_fga, django_user_model, caplog):
    no_sub = django_user_model.objects.create_user(username="local-admin")
    api = _caller(client, no_sub)

    resp = api("post", "grants", _grant())

    assert resp.status_code == 403
    assert "no IdP subject" in resp.json()["detail"]
    assert "has no `sub`" in caplog.text
    assert _checks(fake_fga) == []  # never asks the engine about "user:"


@pytest.mark.django_db
def test_unauthenticated_is_rejected(client, fake_fga):
    resp = client.post(
        "/api/authz/grants", data=json.dumps(_grant()), content_type="application/json"
    )
    assert resp.status_code == 401


# --- grants: what may be written -------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "relation, obj",
    [
        ("parent", "project:1"),  # structural: would re-parent a subtree
        ("platform", "project:1"),  # structural: would grant platform admins data access
        ("project", "sample:1"),  # structural: moves a sample
        ("can_view", "project:1"),  # computed, never a stored tuple
        ("admin", "platform:gx"),  # platform roles are not granted over HTTP
        ("delegate", "platform:gx"),
    ],
)
def test_only_role_relations_are_grantable(api, fake_fga, relation, obj):
    subject = "project:2" if relation in {"parent", "project"} else "user:bob"

    resp = api("post", "grants", {"subject": subject, "relation": relation, "object": obj})

    assert resp.status_code == 422
    assert "cannot be granted" in json.dumps(resp.json())
    assert fake_fga.calls == []  # rejected before any engine call
    assert not GrantAudit.objects.exists()


# --- grants: acting on behalf of an end user -------------------------------


@pytest.mark.django_db
def test_delegate_grants_on_behalf_of_an_admin(client, fake_fga, service_user):
    fake_fga.allowed |= {
        (SERVICE, "delegate", PLATFORM),
        ("user:carol", "can_administer", "project:1"),
    }
    api = _caller(client, service_user)

    resp = api("post", "grants", _grant(on_behalf_of="user:carol"))

    assert resp.status_code == 201
    # authority is checked against carol, not the service
    assert _checks(fake_fga) == [
        (SERVICE, "delegate", PLATFORM, ()),
        ("user:carol", "can_administer", "project:1", PLATFORM_EDGE),
    ]
    audit = GrantAudit.objects.get()
    assert audit.performed_by == service_user
    assert audit.on_behalf_of == "user:carol"


@pytest.mark.django_db
def test_delegate_cannot_exceed_the_end_users_authority(client, fake_fga, service_user):
    fake_fga.allowed.add((SERVICE, "delegate", PLATFORM))
    api = _caller(client, service_user)

    resp = api("post", "grants", _grant(on_behalf_of="user:carol"))

    assert resp.status_code == 403
    assert "user:carol may not manage roles" in resp.json()["detail"]
    assert fake_fga.writes == []


@pytest.mark.django_db
def test_non_delegate_cannot_act_on_behalf_of_anyone(api, fake_fga):
    # alice is a project admin, but not a delegate: naming someone else is refused
    # outright rather than silently checked against alice.
    fake_fga.allowed.add((ALICE, "can_administer", "project:1"))

    resp = api("post", "grants", _grant(on_behalf_of="user:carol"))

    assert resp.status_code == 403
    assert "not a delegate" in resp.json()["detail"]
    assert fake_fga.writes == []


@pytest.mark.django_db
@pytest.mark.parametrize("on_behalf_of", ["user:", "group:lab#member", "user:*", "project:1"])
def test_malformed_on_behalf_of_is_rejected(api, fake_fga, on_behalf_of):
    resp = api("post", "grants", _grant(on_behalf_of=on_behalf_of))

    assert resp.status_code == 422
    assert fake_fga.calls == []


# --- grants: audit and write are one unit ----------------------------------


@pytest.mark.django_db
def test_failed_engine_write_leaves_no_audit_row(api, fake_fga):
    fake_fga.allowed.add((ALICE, "can_administer", "project:1"))
    fake_fga.fail_writes = True

    with pytest.raises(Exception, match="simulated engine write failure"):
        api("post", "grants", _grant())

    assert not GrantAudit.objects.exists()


# --- check / list-objects: who may ask about whom --------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path, body",
    [
        ("check", {"relation": "can_view", "object": "project:1"}),
        ("list-objects", {"relation": "can_view", "type": "project"}),
    ],
)
def test_caller_may_query_itself(api, fake_fga, path, body):
    resp = api("post", path, {"user": ALICE, **body})
    assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path, body",
    [
        ("check", {"relation": "can_view", "object": "project:1"}),
        ("list-objects", {"relation": "can_view", "type": "project"}),
    ],
)
def test_non_delegate_may_not_query_others(api, fake_fga, path, body):
    resp = api("post", path, {"user": "user:bob", **body})

    assert resp.status_code == 403
    # only the delegate question was asked; bob's permissions were not
    assert _checks(fake_fga) == [(ALICE, "delegate", PLATFORM, ())]


@pytest.mark.django_db
def test_delegate_may_query_others(client, fake_fga, service_user):
    fake_fga.allowed |= {(SERVICE, "delegate", PLATFORM), ("user:bob", "can_view", "project:1")}
    api = _caller(client, service_user)

    resp = api("post", "check", {"user": "user:bob", "relation": "can_view", "object": "project:1"})

    assert resp.status_code == 200
    assert resp.json() == {"allowed": True}


def test_relationship_is_hashable_value_object():
    a = fga.Relationship(user="user:x", relation="viewer", object="project:9")
    b = fga.Relationship(user="user:x", relation="viewer", object="project:9")
    assert a == b
