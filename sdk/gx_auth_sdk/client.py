"""OpenFGA decision-engine client (the hot path)."""

from __future__ import annotations

from dataclasses import dataclass

from openfga_sdk import ClientConfiguration
from openfga_sdk.client.models import (
    ClientCheckRequest,
    ClientListObjectsRequest,
    ClientTuple,
    ClientWriteRequest,
)
from openfga_sdk.sync import OpenFgaClient

from .config import get_config
from .ids import validate_object, validate_subject, validate_type


@dataclass(frozen=True)
class Relationship:
    """A relationship tuple: `<relation>` links `user` to `object` (fully-qualified ids)."""

    user: str
    relation: str
    object: str


def _client() -> OpenFgaClient:
    cfg = get_config()
    return OpenFgaClient(ClientConfiguration(api_url=cfg.fga_api_url, store_id=cfg.fga_store_id))


def check(user: str, relation: str, obj: str, context: dict | None = None) -> bool:
    """Return whether `user` has `relation` on `obj`.

    Raises `ValueError` on a malformed id rather than letting the engine answer
    a meaningless question with a plain `False` (see `ids`).
    """
    validate_subject(user, "check() user")
    validate_object(obj, "check() object")
    with _client() as fga:
        resp = fga.check(
            ClientCheckRequest(user=user, relation=relation, object=obj, context=context or None)
        )
    return bool(resp.allowed)


def list_objects(user: str, relation: str, type_: str) -> list[str]:
    """Return fully-qualified object ids (e.g. "sample:1") the user has `relation` on.

    Note: this returns every matching id in the shared store. Callers resolve only
    the ids they own (the object-id space spans services).
    """
    validate_subject(user, "list_objects() user")
    validate_type(type_, "list_objects() type")
    with _client() as fga:
        resp = fga.list_objects(ClientListObjectsRequest(user=user, relation=relation, type=type_))
    return list(resp.objects)


def write_relationship(user: str, relation: str, obj: str) -> None:
    validate_subject(user, "write_relationship() user")
    validate_object(obj, "write_relationship() object")
    with _client() as fga:
        fga.write(
            ClientWriteRequest(writes=[ClientTuple(user=user, relation=relation, object=obj)])
        )


def delete_relationship(user: str, relation: str, obj: str) -> None:
    validate_subject(user, "delete_relationship() user")
    validate_object(obj, "delete_relationship() object")
    with _client() as fga:
        fga.write(
            ClientWriteRequest(deletes=[ClientTuple(user=user, relation=relation, object=obj)])
        )
