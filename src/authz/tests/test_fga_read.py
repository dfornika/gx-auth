"""Translation between the OpenFGA SDK and the wrapper's dataclasses.

The engine's own decisions are not tested here — that is what the model test DSL
is for (`just fga-model-test`, see src/fga/README.md).
"""

import pytest
from openfga_sdk.exceptions import ValidationException

from authz.services import fga


def test_read_tuples_translates_response(fake_fga):
    page = fga.read_tuples()

    assert len(page.tuples) == 7  # the seed fixture
    alice = next(t for t in page.tuples if t.user == "user:alice")
    assert (alice.relation, alice.object) == ("admin", "project:demo")
    assert (alice.object_type, alice.object_id) == ("project", "demo")
    assert alice.timestamp is not None


def test_blank_filters_are_sent_as_none_not_empty_string(fake_fga):
    """An empty string reaches the server and is rejected; None omits the filter."""
    fga.read_tuples(user="", relation="", obj="")

    _, user, relation, obj = fake_fga.calls[0]
    assert (user, relation, obj) == (None, None, None)


def test_read_tuples_paginates_and_terminates(fake_fga):
    seen, token, pages = [], None, 0
    while True:
        page = fga.read_tuples(page_size=3, continuation_token=token)
        seen.extend(page.tuples)
        pages += 1
        token = page.continuation_token
        if not token:
            break

    assert [len(p) for p in (seen[:3], seen[3:6], seen[6:])] == [3, 3, 1]
    assert pages == 3
    assert len({(t.user, t.relation, t.object) for t in seen}) == 7


def test_read_tuples_options_dict_is_not_reused_across_calls(fake_fga):
    """OpenFgaClient.read() pops page_size/continuation_token out of `options`."""
    first = fga.read_tuples(page_size=3)
    second = fga.read_tuples(page_size=3, continuation_token=first.continuation_token)

    assert len(second.tuples) == 3
    assert second.tuples[0] != first.tuples[0]


def test_engine_rejects_relation_only_filter(fake_fga):
    with pytest.raises(ValidationException):
        fga.read_tuples(relation="admin")


def test_engine_accepts_object_type_with_user(fake_fga):
    page = fga.read_tuples(obj="project:", user="user:alice")

    assert [t.object for t in page.tuples] == ["project:demo"]


def test_expand_translates_tuple_to_userset(fake_fga):
    from conftest import _ttu_leaf

    fake_fga.expand_responses[("project:demo-sub", "admin")] = _ttu_leaf(
        "project:demo-sub#parent", "project:demo#admin"
    )

    node = fga.expand("project:demo-sub", "admin")

    assert node.kind == "tuple_to_userset"
    assert node.via == "project:demo-sub#parent"
    assert [(c.kind, c.target) for c in node.children] == [("computed", "project:demo#admin")]
    assert node.children[0].target_object == "project:demo"
    assert node.children[0].target_relation == "admin"


def test_expand_translates_empty_users_leaf(fake_fga):
    from conftest import _users_leaf

    fake_fga.expand_responses[("project:demo", "admin")] = _users_leaf()

    node = fga.expand("project:demo", "admin")

    assert node.kind == "users"
    assert node.users == ()


def test_read_model_splits_storable_from_computed(fake_fga):
    model = fga.read_model()

    project = next(t for t in model.types if t.name == "project")
    assert set(project.storable_relations) == {"parent", "admin", "member", "viewer"}
    assert "can_view" not in project.storable_relations
