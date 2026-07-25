"""Orchestration for the read-only admin inspector.

`fga.py` stays 1:1 with engine calls so the engine remains swappable; everything
that needs *several* calls — recursive expansion, scanning around the engine's
filter limits, building the project hierarchy — lives here. This module talks to
`fga` only, and never imports `openfga_sdk`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from django.conf import settings

from . import fga
from .fga import ExpandNode, ModelSummary, StoredTuple

# Recursive expand budgets. `can_view` on a sample two projects deep already
# costs ~8 calls across 4 levels, so a smaller depth would truncate exactly the
# inheritance the page exists to show.
MAX_DEPTH = 6
MAX_NODES = 100

# Scan mode: the engine cannot filter by relation alone (or by object type
# without an id or user), so those queries read pages and filter here.
SCAN_PAGE_SIZE = 100
SCAN_MAX_TUPLES = 1000


# --- Store status -----------------------------------------------------------


@dataclass(frozen=True)
class StoreStatus:
    """Header strip shown on every inspector page."""

    api_url: str = ""
    store_id: str = ""
    model_id: str = ""
    pinned: bool = False
    latest_model_id: str = ""
    error: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.store_id)

    @property
    def stale_pin(self) -> bool:
        """A pinned FGA_MODEL_ID that is no longer the store's newest model."""
        return bool(
            self.pinned
            and self.model_id
            and self.latest_model_id
            and self.model_id != self.latest_model_id
        )


def store_status() -> StoreStatus:
    """Describe the engine connection. Never raises — errors become `error`."""
    pinned = bool(settings.FGA_MODEL_ID)
    base = StoreStatus(
        api_url=settings.FGA_API_URL,
        store_id=settings.FGA_STORE_ID,
        pinned=pinned,
    )
    if not base.configured:
        return base
    try:
        model = fga.read_model()
        # When nothing is pinned the active model *is* the latest, so the second
        # call is only worth making to detect a stale pin.
        latest = fga.latest_model_id() if pinned else model.id
        return replace(base, model_id=model.id, latest_model_id=latest)
    except Exception as exc:  # surfaced in the strip, never a 500
        return replace(base, error=describe_error(exc))


def describe_error(exc: Exception) -> str:
    """Human-readable one-liner for an engine failure.

    Lives here so views can catch plain `Exception` and never import the SDK.
    """
    if fga.is_unreachable(exc):
        return (
            f"cannot reach OpenFGA at {settings.FGA_API_URL} — "
            f"{getattr(exc, 'reason', None) or exc}. Is the engine running?"
        )
    return f"{type(exc).__name__}: {exc}"


# --- Model-driven form choices ----------------------------------------------


def model_choices() -> tuple[ModelSummary, tuple[str, ...], tuple[str, ...]]:
    """(model, object types, storable relations) read from the *active* model.

    Sourced live rather than from `fga/model.fga` on disk: the store's active
    model is what the engine actually answers with, and the two can drift. Only
    directly-assignable relations are offered — computed ones (`can_view` and
    friends) are never rows in the store, so filtering by them always returns
    nothing.
    """
    model = fga.read_model()
    types = tuple(t.name for t in model.types if t.name != "user")
    relations = sorted({r for t in model.types for r in t.storable_relations})
    return model, types, tuple(relations)


# --- Tuple querying (with scan fallback) ------------------------------------


@dataclass(frozen=True)
class TupleQueryResult:
    tuples: tuple[StoredTuple, ...] = ()
    continuation_token: str = ""
    scanned: bool = False
    scanned_count: int = 0
    scan_capped: bool = False


def engine_can_filter(
    *, object_type: str = "", object_id: str = "", user: str = "", relation: str = ""
) -> bool:
    """Whether the engine will accept this filter combination.

    Its rule, verbatim from a 400: *"the object type field is required and both
    the object id and user cannot be empty"*. Relation may be added to any
    otherwise-valid combination, but is never sufficient on its own.
    """
    if not any((object_type, object_id, user, relation)):
        return True  # no tuple_key at all -> read the whole store
    if not object_type:
        return False
    return bool(object_id or user)


def query_tuples(
    *,
    object_type: str = "",
    object_id: str = "",
    relation: str = "",
    user: str = "",
    page_size: int = 50,
    continuation_token: str = "",
    max_scan: int = SCAN_MAX_TUPLES,
) -> TupleQueryResult:
    """Filtered tuples, pushing the filter to the engine when it will take it.

    When it won't, read pages and filter here, reporting how many tuples were
    scanned so the page can say so plainly. Scans are not paginated — every
    match within the scan cap is returned at once.
    """
    if engine_can_filter(
        object_type=object_type, object_id=object_id, user=user, relation=relation
    ):
        obj = f"{object_type}:{object_id}" if object_type else None
        page = fga.read_tuples(
            user=user or None,
            relation=relation or None,
            obj=obj,
            page_size=page_size,
            continuation_token=continuation_token or None,
        )
        return TupleQueryResult(tuples=page.tuples, continuation_token=page.continuation_token)

    matched: list[StoredTuple] = []
    scanned = 0
    capped = False
    token: str | None = None
    while True:
        page = fga.read_tuples(page_size=SCAN_PAGE_SIZE, continuation_token=token)
        scanned += len(page.tuples)
        matched.extend(
            t for t in page.tuples if _matches(t, object_type, object_id, relation, user)
        )
        token = page.continuation_token
        if not token or not page.tuples:
            break
        if scanned >= max_scan:
            capped = True
            break

    return TupleQueryResult(
        tuples=tuple(matched),
        scanned=True,
        scanned_count=scanned,
        scan_capped=capped,
    )


def _matches(t: StoredTuple, object_type: str, object_id: str, relation: str, user: str) -> bool:
    if object_type and t.object_type != object_type:
        return False
    if object_id and t.object.partition(":")[2] != object_id:
        return False
    if relation and t.relation != relation:
        return False
    if user and t.user != user:
        return False
    return True


# --- Recursive expand -------------------------------------------------------


@dataclass(frozen=True)
class ExpandResult:
    root: ExpandNode
    call_count: int = 0
    truncated: bool = False


def expand_recursive(
    obj: str,
    relation: str,
    *,
    max_depth: int = MAX_DEPTH,
    max_nodes: int = MAX_NODES,
) -> ExpandResult:
    """Follow `expand` through computed and tuple-to-userset edges to the users.

    One engine call resolves a single `object#relation`; every relation in this
    model crosses at least one tuple-to-userset boundary, so a single call never
    reaches a user. Results are memoized on `(object, relation)`, which also
    bounds cycles — the application forbids them at write time, but a
    hand-written tuple could still create one.
    """
    seen: set[tuple[str, str]] = set()
    calls = 0
    truncated = False

    def walk(o: str, r: str, depth: int) -> ExpandNode:
        nonlocal calls, truncated
        label = f"{o}#{r}"
        if (o, r) in seen:
            return ExpandNode(label=label, kind="repeat", target=label)
        if depth > max_depth or calls >= max_nodes:
            truncated = True
            return ExpandNode(label=label, kind="truncated", target=label)
        seen.add((o, r))
        calls += 1
        return descend(fga.expand(o, r), depth)

    def descend(node: ExpandNode, depth: int) -> ExpandNode:
        # A computed node names another object#relation; resolving it is a new
        # engine call, so it costs a level. Structural nodes (union and friends)
        # came from the call we already made, so they do not.
        if node.kind == "computed" and node.target:
            o, sep, r = node.target.partition("#")
            if sep:
                return replace(node, children=(walk(o, r, depth + 1),))
            return node
        if node.children:
            return replace(node, children=tuple(descend(c, depth) for c in node.children))
        return node

    root = walk(obj, relation, 0)
    return ExpandResult(root=root, call_count=calls, truncated=truncated)


def effective_users(obj: str, relation: str) -> tuple[list[str], str]:
    """Flat "who holds this?" via the engine's ListUsers. Returns (users, error).

    Deliberately not computed by folding `expand_recursive`'s tree: a union of
    its user leaves is wrong under intersection/difference, and doing it here
    would reimplement decision logic that belongs in the engine.
    """
    try:
        return fga.list_users(obj, relation), ""
    except Exception as exc:
        return [], describe_error(exc)


# --- Project hierarchy ------------------------------------------------------


@dataclass(frozen=True)
class TreeNode:
    id: str
    children: tuple[TreeNode, ...] = ()

    @property
    def object_id(self) -> str:
        return self.id.partition(":")[2]


@dataclass(frozen=True)
class ProjectTree:
    roots: tuple[TreeNode, ...] = ()
    edge_count: int = 0
    scanned_count: int = 0
    scan_capped: bool = False


def project_tree(*, max_scan: int = SCAN_MAX_TUPLES) -> ProjectTree:
    """The `parent` hierarchy, plus every project that has no parent edge.

    One scan of the store: the engine cannot filter by relation alone, and we
    want the parentless projects too, which a filtered read would not reveal.
    """
    edges: list[tuple[str, str]] = []
    projects: set[str] = set()
    scanned = 0
    capped = False
    token: str | None = None

    while True:
        page = fga.read_tuples(page_size=SCAN_PAGE_SIZE, continuation_token=token)
        scanned += len(page.tuples)
        for t in page.tuples:
            if t.object_type == "project":
                projects.add(t.object)
            # Usersets ("group:lab-x#member") are subjects, not objects.
            if t.user.startswith("project:") and "#" not in t.user:
                projects.add(t.user)
            if (
                t.relation == "parent"
                and t.object_type == "project"
                and t.user.startswith("project:")
                and "#" not in t.user
            ):
                edges.append((t.user, t.object))
        token = page.continuation_token
        if not token or not page.tuples:
            break
        if scanned >= max_scan:
            capped = True
            break

    children: dict[str, list[str]] = {}
    has_parent: set[str] = set()
    for parent, child in edges:
        children.setdefault(parent, []).append(child)
        has_parent.add(child)
        projects.update((parent, child))

    def build(node_id: str, path: frozenset[str]) -> TreeNode:
        if node_id in path:  # defensive: a hand-written tuple could cycle
            return TreeNode(id=f"{node_id} (cycle)")
        return TreeNode(
            id=node_id,
            children=tuple(build(c, path | {node_id}) for c in sorted(children.get(node_id, ()))),
        )

    roots = tuple(build(p, frozenset()) for p in sorted(projects - has_parent))
    return ProjectTree(
        roots=roots,
        edge_count=len(edges),
        scanned_count=scanned,
        scan_capped=capped,
    )
