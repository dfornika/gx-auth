"""Orchestration on top of the thin wrapper: scan fallback, recursion, tree."""

import pytest

from authz.services import inspector

# --- filter capability / scan fallback --------------------------------------


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({}, True),  # no tuple_key at all -> whole store
        ({"object_type": "project", "object_id": "demo"}, True),
        ({"object_type": "project", "user": "user:alice"}, True),
        ({"object_type": "project", "object_id": "demo", "relation": "admin"}, True),
        ({"relation": "admin"}, False),  # relation alone
        ({"user": "user:alice"}, False),  # user alone
        ({"object_type": "project"}, False),  # type with neither id nor user
    ],
)
def test_engine_can_filter_matches_the_servers_rule(kwargs, expected):
    assert inspector.engine_can_filter(**kwargs) is expected


def test_query_tuples_pushes_supported_filters_to_the_engine(fake_fga):
    result = inspector.query_tuples(object_type="project", object_id="demo")

    assert result.scanned is False
    assert len(result.tuples) == 3
    assert fake_fga.calls[0][3] == "project:demo"  # filter went to the engine


def test_query_tuples_scans_when_the_engine_cannot_filter(fake_fga):
    result = inspector.query_tuples(relation="admin")

    assert result.scanned is True
    assert result.scanned_count == 7  # whole seed set read
    assert [t.user for t in result.tuples] == ["user:alice"]
    # every engine read was unfiltered; the filtering happened here
    assert all(c[2] is None for c in fake_fga.calls if c[0] == "read")


def test_scan_reports_when_it_hits_the_cap(fake_fga, monkeypatch):
    # The cap can only bite when the store is larger than one page.
    monkeypatch.setattr(inspector, "SCAN_PAGE_SIZE", 2)

    result = inspector.query_tuples(relation="admin", max_scan=3)

    assert result.scan_capped is True
    assert result.scanned_count == 4  # stopped after the page that crossed the cap


def test_scan_is_not_capped_when_the_store_fits(fake_fga):
    result = inspector.query_tuples(relation="admin", max_scan=3)

    assert result.scan_capped is False
    assert result.scanned_count == 7


def test_scan_matches_usersets_and_relations_outside_the_model(fake_fga):
    """A store outlives its models; the browser must still find old tuples."""
    fake_fga.tuples.append(("group:lab-x#member", "viewer", "project:child"))

    result = inspector.query_tuples(user="group:lab-x#member")

    assert result.scanned is True
    assert [t.object for t in result.tuples] == ["project:child"]


# --- recursive expand -------------------------------------------------------


@pytest.fixture
def inherited_admin(fake_fga):
    """demo-sub has no direct admin; it inherits alice from its parent demo."""
    from conftest import _ttu_leaf, _union, _users_leaf

    fake_fga.expand_responses.update(
        {
            ("project:demo-sub", "admin"): _union(
                _users_leaf(), _ttu_leaf("project:demo-sub#parent", "project:demo#admin")
            ),
            ("project:demo", "admin"): _union(
                _users_leaf("user:alice"), _ttu_leaf("project:demo#parent")
            ),
        }
    )
    return fake_fga


def test_expand_recursive_resolves_inherited_access(inherited_admin):
    result = inspector.expand_recursive("project:demo-sub", "admin")

    assert result.truncated is False
    assert result.call_count == 2  # one per object#relation, not per node
    assert inherited_admin.expand_calls == 2

    users = _collect_users(result.root)
    assert users == ["user:alice"]


def test_expand_recursive_memoizes_repeat_visits(fake_fga):
    from conftest import _ttu_leaf, _union, _users_leaf

    # Two branches converging on the same object#relation.
    fake_fga.expand_responses.update(
        {
            ("project:a", "admin"): _union(
                _ttu_leaf("project:a#parent", "project:shared#admin"),
                _ttu_leaf("project:a#other", "project:shared#admin"),
            ),
            ("project:shared", "admin"): _users_leaf("user:alice"),
        }
    )

    result = inspector.expand_recursive("project:a", "admin")

    assert result.call_count == 2  # shared expanded once, not twice
    assert _kinds(result.root).count("repeat") == 1


def test_expand_recursive_terminates_on_a_cycle(fake_fga):
    from conftest import _ttu_leaf

    fake_fga.expand_responses.update(
        {
            ("project:a", "admin"): _ttu_leaf("project:a#parent", "project:b#admin"),
            ("project:b", "admin"): _ttu_leaf("project:b#parent", "project:a#admin"),
        }
    )

    result = inspector.expand_recursive("project:a", "admin")

    assert result.call_count == 2
    assert "repeat" in _kinds(result.root)


def test_expand_recursive_truncates_at_the_depth_limit(fake_fga):
    from conftest import _ttu_leaf

    # An unbounded chain: a -> a1 -> a2 -> ...
    class Chain(dict):
        def __contains__(self, key):
            return True

        def __getitem__(self, key):
            obj, _rel = key
            n = int(obj.split(":")[1]) + 1
            return _ttu_leaf(f"{obj}#parent", f"project:{n}#admin")

    fake_fga.expand_responses = Chain()

    result = inspector.expand_recursive("project:0", "admin", max_depth=3)

    assert result.truncated is True
    assert result.call_count == 4  # depths 0..3
    truncated = [n for n in _walk(result.root) if n.kind == "truncated"]
    assert truncated and truncated[0].target_object == "project:4"


# --- project tree -----------------------------------------------------------


def test_project_tree_nests_children_and_keeps_parentless_projects(fake_fga):
    tree = inspector.project_tree()

    roots = {r.id: r for r in tree.roots}
    assert "project:demo" in roots
    assert [c.id for c in roots["project:demo"].children] == ["project:demo-sub"]
    assert tree.edge_count == 1
    assert roots["project:demo"].object_id == "demo"


def test_project_tree_ignores_userset_subjects(fake_fga):
    fake_fga.tuples.append(("group:lab-x#member", "viewer", "project:demo"))

    tree = inspector.project_tree()

    assert all("#" not in r.id for r in tree.roots)


def test_project_tree_survives_a_cycle_below_a_root(fake_fga):
    """r -> a -> b -> a. The model forbids cycles at write time; a hand-written
    tuple could still make one, and the page must not recurse forever."""
    fake_fga.tuples.extend(
        [
            ("project:r", "parent", "project:a"),
            ("project:a", "parent", "project:b"),
            ("project:b", "parent", "project:a"),
        ]
    )

    tree = inspector.project_tree()

    r = next(root for root in tree.roots if root.id == "project:r")
    ids = [n.id for n in _walk_tree(r)]
    assert "project:a (cycle)" in ids


# --- helpers ----------------------------------------------------------------


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _walk_tree(node):
    yield node
    for child in node.children:
        yield from _walk_tree(child)


def _kinds(node):
    return [n.kind for n in _walk(node)]


def _collect_users(node):
    return sorted({u for n in _walk(node) for u in n.users})
