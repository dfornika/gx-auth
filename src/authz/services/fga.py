"""Thin wrapper around the OpenFGA Python SDK.

This is the ONE place the rest of gx-auth (and, over HTTP, the sibling services)
talk to the decision engine. Keeping it thin means the engine stays swappable
(see ADR 0001) and there is a single spot to adjust for SDK version changes.

NOTE: the openfga-sdk surface should be confirmed against the pinned version on
first `uv sync`; the calls below target the >=0.9 sync client.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from openfga_sdk import ClientConfiguration
from openfga_sdk.client.models import (
    ClientCheckRequest,
    ClientListObjectsRequest,
    ClientTuple,
    ClientWriteRequest,
)
from openfga_sdk.sync import OpenFgaClient


def _configuration() -> ClientConfiguration:
    return ClientConfiguration(
        api_url=settings.FGA_API_URL,
        store_id=settings.FGA_STORE_ID or None,
        authorization_model_id=settings.FGA_MODEL_ID or None,
    )


def _client() -> OpenFgaClient:
    return OpenFgaClient(_configuration())


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
