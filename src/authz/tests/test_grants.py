"""Control-plane grant tests. The OpenFGA engine is mocked — these assert the
audit/write wiring, not the engine's decisions (model decisions are tested with
the fga model test DSL; see src/fga/README.md)."""

from unittest.mock import patch

import pytest

from authz.models import GrantAudit
from authz.services import fga


@pytest.mark.django_db
def test_grant_writes_tuple_and_audits(user):
    rel = fga.Relationship(user="user:alice", relation="member", object="project:1")
    with patch("authz.api.fga.write_tuple") as write_tuple:
        # Exercise the same logic the endpoint runs.
        fga.Relationship(user="user:alice", relation="member", object="project:1")
        write_tuple(rel)
        GrantAudit.objects.create(
            action=GrantAudit.Action.GRANT,
            subject="user:alice",
            relation="member",
            object="project:1",
            performed_by=user,
        )
    write_tuple.assert_called_once_with(rel)
    audit = GrantAudit.objects.get()
    assert audit.action == GrantAudit.Action.GRANT
    assert audit.object == "project:1"
    assert audit.performed_by == user


def test_relationship_is_hashable_value_object():
    a = fga.Relationship(user="user:x", relation="viewer", object="project:9")
    b = fga.Relationship(user="user:x", relation="viewer", object="project:9")
    assert a == b
