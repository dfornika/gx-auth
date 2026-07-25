import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openfga_sdk import (
    AuthorizationModel,
    Computed,
    ExpandResponse,
    FgaObject,
    Leaf,
    ListUsersResponse,
    Metadata,
    Node,
    Nodes,
    ReadAuthorizationModelResponse,
    ReadResponse,
    RelationMetadata,
    RelationReference,
    Tuple,
    TupleKey,
    User,
    Users,
    UsersetTree,
    UsersetTreeTupleToUserset,
)
from openfga_sdk.exceptions import ValidationException

SEED_CSV = Path(__file__).resolve().parent / "fga" / "seed.tuples.csv"


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    """Use unhashed static URLs in tests.

    Settings use whitenoise's CompressedManifestStaticFilesStorage, whose
    manifest is produced by `collectstatic` during the image build at
    /src/static — which the compose bind mount then shadows. Any template
    rendering {% static %} (i.e. every admin page) would raise. Nothing here
    tests asset hashing.
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        username="alice", email="alice@example.org", sub="cognito-sub-alice"
    )


# --- OpenFGA fake -----------------------------------------------------------
#
# Patches `authz.services.fga._client` rather than the module's public functions,
# so the SDK -> dataclass translation (the part most likely to be wrong) is
# actually exercised. Returns real SDK response objects.


def load_seed_tuples() -> list[tuple[str, str, str]]:
    """(user, relation, object) triples from the same CSV `just fga-seed` loads.

    Sharing the fixture file means the fake and the real store cannot drift.
    """
    with SEED_CSV.open() as fh:
        return [
            (
                f"{row['user_type']}:{row['user_id']}"
                + (f"#{row['user_relation']}" if row["user_relation"] else ""),
                row["relation"],
                f"{row['object_type']}:{row['object_id']}",
            )
            for row in csv.DictReader(fh)
        ]


def _users_leaf(*users: str) -> Node:
    return Node(name="n", leaf=Leaf(users=Users(users=list(users))))


def _ttu_leaf(tupleset: str, *computed: str) -> Node:
    return Node(
        name="n",
        leaf=Leaf(
            tuple_to_userset=UsersetTreeTupleToUserset(
                tupleset=tupleset, computed=[Computed(userset=c) for c in computed]
            )
        ),
    )


def _union(*nodes: Node, name: str = "n") -> Node:
    return Node(name=name, union=Nodes(nodes=list(nodes)))


class FakeFgaClient:
    """Stands in for `openfga_sdk.sync.OpenFgaClient`.

    `read` reproduces the server's real filter rule — object type required, and
    at least one of object id / user non-empty — so tests cannot bless a
    combination the engine rejects.
    """

    def __init__(self, tuples=None, expand=None, users=None, model=None, latest_model=None):
        self.tuples = list(tuples if tuples is not None else load_seed_tuples())
        self.expand_responses = dict(expand or {})  # (object, relation) -> Node
        self.users = list(users or [])
        self.model = model  # what a pinned FGA_MODEL_ID resolves to
        self.latest_model = latest_model  # set to simulate a stale pin
        self.calls: list[tuple] = []

    # context-manager surface used by fga._client()
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass

    def read(self, body, options=None):
        self.calls.append(("read", body.user, body.relation, body.object))
        options = options or {}
        page_size = options.pop("page_size", 50) or 50
        token = options.pop("continuation_token", None)

        if body.user is not None or body.relation is not None or body.object is not None:
            obj_type, _, obj_id = (body.object or "").partition(":")
            if not obj_type or not (obj_id or body.user):
                raise ValidationException(
                    status=400,
                    reason=(
                        "the 'tuple_key' field was provided but the object type "
                        "field is required and both the object id and user cannot be empty"
                    ),
                )

        matched = [
            t for t in self.tuples if self._matches(t, body.user, body.relation, body.object)
        ]
        start = int(token) if token else 0
        window = matched[start : start + page_size]
        nxt = start + page_size
        return ReadResponse(
            tuples=[
                Tuple(
                    key=TupleKey(user=u, relation=r, object=o),
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                )
                for u, r, o in window
            ],
            continuation_token=str(nxt) if nxt < len(matched) else "",
        )

    @staticmethod
    def _matches(t, user, relation, obj):
        u, r, o = t
        if user and u != user:
            return False
        if relation and r != relation:
            return False
        if obj:
            obj_type, _, obj_id = obj.partition(":")
            if obj_id:
                if o != obj:
                    return False
            elif o.partition(":")[0] != obj_type:
                return False
        return True

    def expand(self, body, options=None):
        key = (body.object, body.relation)
        self.calls.append(("expand", *key))
        if key not in self.expand_responses:
            raise AssertionError(f"unexpected expand of {key}")
        return ExpandResponse(tree=UsersetTree(root=self.expand_responses[key]))

    def list_users(self, body, options=None):
        self.calls.append(("list_users", body.object.type, body.object.id, body.relation))
        return ListUsersResponse(
            users=[
                User(object=FgaObject(type=u.partition(":")[0], id=u.partition(":")[2]))
                for u in self.users
            ]
        )

    def read_latest_authorization_model(self, options=None):
        self.calls.append(("read_latest_authorization_model",))
        return ReadAuthorizationModelResponse(authorization_model=self.latest_model or self.model)

    def read_authorization_model(self, options=None):
        self.calls.append(("read_authorization_model",))
        return ReadAuthorizationModelResponse(authorization_model=self.model)

    @property
    def expand_calls(self) -> int:
        return sum(1 for c in self.calls if c[0] == "expand")


def build_model(model_id="01TESTMODEL0000000000000000"):
    """A stand-in for the project/sample model, with the storable-vs-computed
    split expressed the way the engine does: via directly_related_user_types."""

    def rel_meta(*types):
        return RelationMetadata(
            directly_related_user_types=[RelationReference(type=t) for t in types]
        )

    from openfga_sdk import TypeDefinition, Userset

    any_userset = Userset(this={})
    return AuthorizationModel(
        id=model_id,
        schema_version="1.1",
        type_definitions=[
            TypeDefinition(type="user"),
            TypeDefinition(
                type="project",
                relations={
                    "parent": any_userset,
                    "admin": any_userset,
                    "member": any_userset,
                    "viewer": any_userset,
                    "can_view": any_userset,
                },
                metadata=Metadata(
                    relations={
                        "parent": rel_meta("project"),
                        "admin": rel_meta("user"),
                        "member": rel_meta("user"),
                        "viewer": rel_meta("user"),
                        "can_view": RelationMetadata(directly_related_user_types=[]),
                    }
                ),
            ),
            TypeDefinition(
                type="sample",
                relations={"project": any_userset, "can_view": any_userset},
                metadata=Metadata(
                    relations={
                        "project": rel_meta("project"),
                        "can_view": RelationMetadata(directly_related_user_types=[]),
                    }
                ),
            ),
        ],
    )


@pytest.fixture
def fake_fga(monkeypatch, settings):
    """Patch the engine client. Tests may mutate `fake.tuples` / `expand_responses`."""
    settings.FGA_STORE_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    settings.FGA_MODEL_ID = ""
    fake = FakeFgaClient(model=build_model())
    monkeypatch.setattr("authz.services.fga._client", lambda *a, **kw: fake)
    return fake


@pytest.fixture
def superuser(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="root", email="root@example.org", password="pw"
    )
