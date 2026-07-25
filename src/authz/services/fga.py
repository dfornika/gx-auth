"""Thin wrapper around the OpenFGA Python SDK.

This is the ONE place the rest of gx-auth (and, over HTTP, the sibling services)
talk to the decision engine. Keeping it thin means the engine stays swappable
(see ADR 0001) and there is a single spot to adjust for SDK version changes.

NOTE: the openfga-sdk surface should be confirmed against the pinned version on
first `uv sync`; the calls below target the >=0.9 sync client.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from openfga_sdk import (
    ClientConfiguration,
    FgaObject,
    ReadRequestTupleKey,
    UserTypeFilter,
)
from openfga_sdk.client.models import (
    ClientCheckRequest,
    ClientExpandRequest,
    ClientListObjectsRequest,
    ClientTuple,
    ClientWriteRequest,
)

# `ClientListUsersRequest` is NOT re-exported from openfga_sdk.client.models in
# 0.10.4 (only the non-Client `ListUsersRequest` is) — import it from the submodule.
from openfga_sdk.client.models.list_users_request import ClientListUsersRequest
from openfga_sdk.configuration import RetryParams
from openfga_sdk.sync import OpenFgaClient


def _configuration(
    timeout_millisec: int | None = None, retry_params: RetryParams | None = None
) -> ClientConfiguration:
    return ClientConfiguration(
        api_url=settings.FGA_API_URL,
        store_id=settings.FGA_STORE_ID or None,
        authorization_model_id=settings.FGA_MODEL_ID or None,
        # None -> the SDK's own defaults (timeout 5000 * 60 ms, 3 retries).
        timeout_millisec=timeout_millisec,
        retry_params=retry_params,
    )


def _client(
    timeout_millisec: int | None = None,
    retry_params: RetryParams | None = None,
    connection_retries: int | None = None,
) -> OpenFgaClient:
    """The single place a client is built — tests patch this."""
    config = _configuration(timeout_millisec, retry_params)
    if connection_retries is not None:
        # RetryParams only governs the SDK's own retry loop. Connection-level
        # retries happen a layer below, in urllib3, and dominate the wait when
        # the engine's DNS name does not resolve; sync/rest.py forwards this
        # attribute to the PoolManager if it is set.
        config.retries = connection_retries
    return OpenFgaClient(config)


def _inspect_client() -> OpenFgaClient:
    """Client for the read-only inspector.

    The SDK's default timeout is five minutes, and it retries three times with
    backoff on top — a down engine would hang an admin page for far longer than
    anyone will wait. Fail fast here; the decision hot path (`check` /
    `list_objects`) deliberately keeps the SDK defaults.
    """
    return _client(
        settings.FGA_INSPECTOR_TIMEOUT_MS,
        RetryParams(max_retry=0, min_wait_in_ms=100),
        connection_retries=0,
    )


def is_unreachable(exc: Exception) -> bool:
    """Whether `exc` means the engine could not be reached at all.

    Transport failures escape the SDK as raw urllib3 errors with no `status`,
    rather than as `ApiException(status=0)` — so the obvious check is not enough.
    Lives here because recognising the engine's failure modes is the wrapper's
    job, not its callers'.
    """
    if getattr(exc, "status", None) == 0:
        return True
    if isinstance(exc, OSError):
        return True
    return type(exc).__module__.split(".")[0] == "urllib3"


@dataclass(frozen=True)
class Relationship:
    """A single relationship tuple: `<relation>` links `user` to `object`.

    `user` / `object` are fully-qualified FGA ids, e.g. "user:abc",
    "project:42", or a userset like "group:lab-x#member".
    """

    user: str
    relation: str
    object: str


def check(
    user: str,
    relation: str,
    obj: str,
    *,
    context: dict | None = None,
    contextual_tuples: list[Relationship] | None = None,
) -> bool:
    """Return whether `user` has `relation` on `obj`.

    `context` supplies condition parameters (e.g. {"required_level": 3}).
    `contextual_tuples` assert not-yet-persisted relationships for
    read-after-write flows (see docs/003-integration-and-sync.md).
    """
    ctx_tuples = [
        ClientTuple(user=t.user, relation=t.relation, object=t.object)
        for t in (contextual_tuples or [])
    ]
    with _client() as fga:
        resp = fga.check(
            ClientCheckRequest(
                user=user,
                relation=relation,
                object=obj,
                context=context or None,
                contextual_tuples=ctx_tuples or None,
            )
        )
    return bool(resp.allowed)


def list_objects(user: str, relation: str, type_: str, *, context: dict | None = None) -> list[str]:
    """Return the ids of objects of `type_` on which `user` has `relation`.

    Heavier than `check`; watch performance at scale (docs/003).
    """
    with _client() as fga:
        resp = fga.list_objects(
            ClientListObjectsRequest(
                user=user, relation=relation, type=type_, context=context or None
            )
        )
    return list(resp.objects)


def write_tuple(rel: Relationship) -> None:
    with _client() as fga:
        fga.write(
            ClientWriteRequest(
                writes=[ClientTuple(user=rel.user, relation=rel.relation, object=rel.object)]
            )
        )


def delete_tuple(rel: Relationship) -> None:
    with _client() as fga:
        fga.write(
            ClientWriteRequest(
                deletes=[ClientTuple(user=rel.user, relation=rel.relation, object=rel.object)]
            )
        )


# --- Read-only inspection ---------------------------------------------------
#
# Everything below is used by the admin inspector (authz/services/inspector.py).
# Each function maps 1:1 onto a single engine call; orchestration (recursion,
# scanning, budgets) belongs in `inspector`, not here. SDK objects never cross
# this boundary — callers get the plain dataclasses defined below.


@dataclass(frozen=True)
class StoredTuple:
    """A tuple as it exists in the store, with the engine's write timestamp."""

    user: str
    relation: str
    object: str
    timestamp: datetime | None = None

    @property
    def object_type(self) -> str:
        return self.object.partition(":")[0]

    @property
    def object_id(self) -> str:
        return self.object.partition(":")[2]


@dataclass(frozen=True)
class TuplePage:
    tuples: tuple[StoredTuple, ...] = ()
    continuation_token: str = ""  # "" == no further pages


@dataclass(frozen=True)
class ExpandNode:
    """One node of OpenFGA's UsersetTree, translated to an engine-agnostic shape.

    `kind` is one of: union, intersection, difference, users, computed,
    tuple_to_userset, empty — plus `repeat` and `truncated`, which `inspector`
    synthesises during recursion.
    """

    label: str = ""
    kind: str = "empty"
    users: tuple[str, ...] = ()  # kind == "users"
    target: str = ""  # "object#relation" — kind in {computed, truncated, repeat}
    via: str = ""  # tupleset, e.g. "project:demo-sub#parent"
    children: tuple[ExpandNode, ...] = ()

    @property
    def target_object(self) -> str:
        return self.target.partition("#")[0]

    @property
    def target_relation(self) -> str:
        return self.target.partition("#")[2]


@dataclass(frozen=True)
class RelationInfo:
    name: str
    #: True when the relation has directly-related user types, i.e. it can be
    #: written as a tuple. Computed relations (`can_view` and friends) are False
    #: and are never rows in the store.
    directly_assignable: bool


@dataclass(frozen=True)
class TypeInfo:
    name: str
    relations: tuple[RelationInfo, ...] = ()

    @property
    def storable_relations(self) -> tuple[str, ...]:
        return tuple(r.name for r in self.relations if r.directly_assignable)


@dataclass(frozen=True)
class ModelSummary:
    id: str = ""
    types: tuple[TypeInfo, ...] = ()


def read_tuples(
    *,
    user: str | None = None,
    relation: str | None = None,
    obj: str | None = None,
    page_size: int = 50,
    continuation_token: str | None = None,
) -> TuplePage:
    """Read stored tuples, optionally filtered.

    The engine's filter rules are narrow — it rejects a tuple_key unless the
    object *type* is given AND at least one of the object id / user is non-empty.
    Passing every filter as None omits the tuple_key entirely and reads the whole
    store. Blank filters must therefore be None, never "": an empty string is
    sent to the server and rejected. `inspector.query_tuples` owns working
    around these rules; this function just reports what the engine says.
    """
    body = ReadRequestTupleKey(
        user=user or None,
        relation=relation or None,
        object=obj or None,
    )
    # Fresh dict every call: OpenFgaClient.read() *pops* page_size and
    # continuation_token out of whatever dict it is handed.
    options: dict = {"page_size": page_size}
    if continuation_token:
        options["continuation_token"] = continuation_token

    with _inspect_client() as fga:
        resp = fga.read(body, options)

    return TuplePage(
        tuples=tuple(
            StoredTuple(
                user=t.key.user,
                relation=t.key.relation,
                object=t.key.object,
                timestamp=t.timestamp,
            )
            for t in (resp.tuples or [])
        ),
        continuation_token=resp.continuation_token or "",
    )


def expand(obj: str, relation: str) -> ExpandNode:
    """Expand one `object#relation` into its userset tree — exactly one call.

    The tree is not transitively resolved: a `tuple_to_userset` node names the
    usersets to follow but does not follow them. `inspector.expand_recursive`
    does the walking.
    """
    with _inspect_client() as fga:
        resp = fga.expand(ClientExpandRequest(relation=relation, object=obj))
    return _to_node(resp.tree.root if resp.tree else None)


def list_users(obj: str, relation: str, *, user_types: tuple[str, ...] = ("user",)) -> list[str]:
    """Return the subjects that hold `relation` on `obj`, per the engine.

    Used instead of folding `expand`'s tree: a union of the tree's user leaves is
    wrong under intersection/difference, and computing it here would reimplement
    decision logic that belongs in the engine.
    """
    obj_type, _, obj_id = obj.partition(":")
    with _inspect_client() as fga:
        resp = fga.list_users(
            ClientListUsersRequest(
                object=FgaObject(type=obj_type, id=obj_id),
                relation=relation,
                user_filters=[UserTypeFilter(type=t) for t in user_types],
            )
        )
    return [_format_user(u) for u in (resp.users or [])]


def read_model() -> ModelSummary:
    """The authorization model currently in force for this store."""
    with _inspect_client() as fga:
        # read_authorization_model() requires a configured id; when FGA_MODEL_ID
        # is blank the store's latest model is the one being used.
        resp = (
            fga.read_authorization_model()
            if settings.FGA_MODEL_ID
            else fga.read_latest_authorization_model()
        )
    return _to_model_summary(resp.authorization_model)


def latest_model_id() -> str:
    """Id of the newest model in the store, for drift display against a pin."""
    with _inspect_client() as fga:
        resp = fga.read_latest_authorization_model()
    return getattr(resp.authorization_model, "id", "") or ""


# --- SDK -> dataclass translation -------------------------------------------


def _format_user(u) -> str:
    if getattr(u, "object", None) is not None:
        return f"{u.object.type}:{u.object.id}"
    if getattr(u, "wildcard", None) is not None:
        return f"{u.wildcard.type}:*"
    us = getattr(u, "userset", None)
    if us is not None:
        return f"{us.type}:{us.id}#{us.relation}"
    return str(u)


def _to_node(node) -> ExpandNode:
    """Translate an SDK `Node` into an `ExpandNode`. Total: never raises.

    `node.name` is display-only — union children repeat their parent's name, so
    never branch on it.
    """
    if node is None:
        return ExpandNode(kind="empty")

    label = node.name or ""

    if node.union is not None:
        return ExpandNode(
            label=label,
            kind="union",
            children=tuple(_to_node(n) for n in (node.union.nodes or [])),
        )
    if node.intersection is not None:
        return ExpandNode(
            label=label,
            kind="intersection",
            children=tuple(_to_node(n) for n in (node.intersection.nodes or [])),
        )
    if node.difference is not None:
        return ExpandNode(
            label=label,
            kind="difference",
            children=(
                _to_node(node.difference.base),
                _to_node(node.difference.subtract),
            ),
        )

    leaf = node.leaf
    if leaf is not None:
        if leaf.users is not None:
            # May legitimately be empty, e.g. a project with no direct admins.
            return ExpandNode(label=label, kind="users", users=tuple(leaf.users.users or ()))
        if leaf.computed is not None:
            return ExpandNode(label=label, kind="computed", target=leaf.computed.userset or "")
        ttu = leaf.tuple_to_userset
        if ttu is not None:
            # The engine has already resolved the tupleset, so `computed` names
            # the usersets to follow next.
            return ExpandNode(
                label=label,
                kind="tuple_to_userset",
                via=ttu.tupleset or "",
                children=tuple(
                    ExpandNode(label=c.userset or "", kind="computed", target=c.userset or "")
                    for c in (ttu.computed or [])
                ),
            )

    return ExpandNode(label=label, kind="empty")


def _to_model_summary(am) -> ModelSummary:
    if am is None:
        return ModelSummary()

    types = []
    for td in sorted(am.type_definitions or [], key=lambda t: t.type):
        meta_rels = {}
        if td.metadata is not None and td.metadata.relations:
            meta_rels = td.metadata.relations
        relations = tuple(
            RelationInfo(
                name=name,
                directly_assignable=bool(
                    getattr(meta_rels.get(name), "directly_related_user_types", None)
                ),
            )
            for name in sorted((td.relations or {}).keys())
        )
        types.append(TypeInfo(name=td.type, relations=relations))

    return ModelSummary(id=am.id or "", types=tuple(types))
