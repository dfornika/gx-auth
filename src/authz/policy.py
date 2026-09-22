"""Who may use the control plane — gx-auth's authorization of its own API.

Every rule here is answered by OpenFGA through `services.fga`; this module only
decides *which* questions to ask. It holds no decision logic of its own
(CLAUDE.md), just two things the engine cannot express: which relations the
grants API is allowed to write at all, and whose authority a request carries.

The actor model (ADR 0004):

- By default the **actor** is the caller: the principal the API key belongs to.
- A caller holding `delegate` on the platform may instead name the end user it
  acts for (`on_behalf_of`). The actor is then that user, and the caller is
  recorded alongside it. This is how a service like SDS carries the person who
  clicked "add member" into gx-auth, rather than every grant reading "SDS did
  it".

A principal with no IdP `sub` has no subject (ADR 0003), so it can be neither
caller-as-actor nor delegate: such requests are denied, with a log line that
says why.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from .services import fga

logger = logging.getLogger(__name__)

#: object type -> the relations the grants API may write on it. Role
#: relations only. Structural edges (`project#parent`, `sample#project`,
#: `project#platform`) change what a grant *means* across a whole subtree and
#: belong to resource sync, not to role management. Platform roles are written
#: by the `grant_platform_role` management command, not over HTTP.
GRANTABLE_RELATIONS: dict[str, frozenset[str]] = {
    "project": frozenset({"admin", "member", "viewer"}),
}


class Forbidden(Exception):
    """The request is authenticated but not allowed. `str()` is safe to return."""


def platform_object() -> str:
    return f"platform:{settings.GXAUTH_PLATFORM_ID}"


def is_grantable(relation: str, obj: str) -> bool:
    obj_type = obj.partition(":")[0]
    return relation in GRANTABLE_RELATIONS.get(obj_type, frozenset())


@dataclass(frozen=True)
class Actor:
    """Whose authority a request is decided on.

    `subject` is the principal the permission check runs against. `delegate`
    is the calling service's subject when it acted on someone's behalf, else
    None.
    """

    subject: str
    delegate: str | None = None


def _caller_subject(caller) -> str:
    subject = caller.fga_subject
    if subject is None:
        logger.error(
            "control plane: caller id=%s (%s) has no `sub`, so no OpenFGA subject; denying",
            caller.pk,
            caller.username,
        )
        raise Forbidden("Caller has no IdP subject, so holds no authorization (ADR 0003).")
    return subject


def is_delegate(subject: str) -> bool:
    return fga.check(subject, "delegate", platform_object())


def resolve_actor(caller, on_behalf_of: str | None) -> Actor:
    """The actor for a request from `caller`, optionally acting for someone else.

    Raises `Forbidden` if the caller has no subject, or names an
    `on_behalf_of` without being a platform delegate.
    """
    caller_subject = _caller_subject(caller)
    if not on_behalf_of:
        return Actor(subject=caller_subject)
    if not is_delegate(caller_subject):
        raise Forbidden(
            f"{caller_subject} may not act on behalf of another user: "
            f"it is not a delegate on {platform_object()}."
        )
    return Actor(subject=on_behalf_of, delegate=caller_subject)


def can_manage_grants(actor: Actor, obj: str) -> bool:
    """May `actor` grant or revoke roles on `obj`?

    Asks the engine for `can_administer`, with the object's platform edge
    supplied as a contextual tuple. Platform admins can therefore manage grants
    on every project, including a new one with no admin yet, without that edge
    being stored. Leaving it unstored keeps platform admins out of project
    *data* on the hot path: to read a project they must grant themselves a
    role, and that grant is audited.
    """
    return fga.check(
        actor.subject,
        "can_administer",
        obj,
        contextual_tuples=[
            fga.Relationship(user=platform_object(), relation="platform", object=obj)
        ],
    )


def ensure_can_query(caller, subject: str) -> None:
    """A caller may ask `check`/`list-objects` about itself; asking about any
    other subject requires being a platform delegate.
    """
    caller_subject = _caller_subject(caller)
    if subject == caller_subject:
        return
    if not is_delegate(caller_subject):
        raise Forbidden(
            f"{caller_subject} may only query its own permissions: "
            f"it is not a delegate on {platform_object()}."
        )
