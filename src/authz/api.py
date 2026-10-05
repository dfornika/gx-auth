"""Authorization control-plane API.

- `check` / `list-objects`: thin, audited wrappers over the OpenFGA engine, for
  callers that prefer a domain API. Hot-path callers may also hit OpenFGA
  directly (see docs/001).
- `grants`: the audited write path — domain grant/revoke that translates into
  tuple writes and records a GrantAudit row (see docs/003).

Every endpoint is authorized against gx-auth's own model (`policy`, ADR 0004):
a caller queries only its own permissions unless it is a platform delegate,
and manages grants on a project only if the actor holds `can_administer` there.
"""

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import field_validator, model_validator

from . import policy
from .models import GrantAudit
from .services import fga, grants
from .validators import validate_object, validate_relation, validate_subject, validate_type_name

router = Router(tags=["authz"])


# --- Check -----------------------------------------------------------------


class CheckIn(Schema):
    user: str  # e.g. "user:abc"
    relation: str  # e.g. "can_view"
    object: str  # e.g. "sample:42"
    context: dict | None = None  # condition params, e.g. {"required_level": 3}

    @field_validator("user")
    @classmethod
    def _user_is_valid_subject(cls, v: str) -> str:
        return validate_subject(v)

    @field_validator("relation")
    @classmethod
    def _relation_is_valid(cls, v: str) -> str:
        return validate_relation(v)

    @field_validator("object")
    @classmethod
    def _object_is_valid(cls, v: str) -> str:
        return validate_object(v)


class CheckOut(Schema):
    allowed: bool


def _ensure_can_query(request, subject: str) -> None:
    try:
        policy.ensure_can_query(request.user, subject)
    except policy.Forbidden as exc:
        raise HttpError(403, str(exc)) from exc


@router.post("/check", response=CheckOut)
def check(request, payload: CheckIn):
    _ensure_can_query(request, payload.user)
    allowed = fga.check(payload.user, payload.relation, payload.object, context=payload.context)
    return {"allowed": allowed}


# --- List objects ----------------------------------------------------------


class ListObjectsIn(Schema):
    user: str
    relation: str
    type: str  # object type, e.g. "sample"
    context: dict | None = None

    @field_validator("user")
    @classmethod
    def _user_is_valid_subject(cls, v: str) -> str:
        return validate_subject(v)

    @field_validator("relation")
    @classmethod
    def _relation_is_valid(cls, v: str) -> str:
        return validate_relation(v)

    @field_validator("type")
    @classmethod
    def _type_is_valid(cls, v: str) -> str:
        return validate_type_name(v)


class ListObjectsOut(Schema):
    objects: list[str]


@router.post("/list-objects", response=ListObjectsOut)
def list_objects(request, payload: ListObjectsIn):
    _ensure_can_query(request, payload.user)
    objects = fga.list_objects(
        payload.user, payload.relation, payload.type, context=payload.context
    )
    return {"objects": objects}


# --- Grants (audited write path) -------------------------------------------


class GrantIn(Schema):
    subject: str  # "user:abc" or a userset like "group:lab-x#member"
    relation: str  # role, e.g. "member"
    object: str  # "project:42"
    reason: str = ""
    # The end user a platform delegate (e.g. a consuming service) acts for. The
    # grant is authorized against this user's permissions, not the caller's.
    on_behalf_of: str | None = None

    @field_validator("subject")
    @classmethod
    def _subject_is_valid(cls, v: str) -> str:
        return validate_subject(v, "subject")

    @field_validator("relation")
    @classmethod
    def _relation_is_valid(cls, v: str) -> str:
        return validate_relation(v)

    @field_validator("object")
    @classmethod
    def _object_is_valid(cls, v: str) -> str:
        return validate_object(v)

    @field_validator("on_behalf_of")
    @classmethod
    def _on_behalf_of_is_valid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        validate_subject(v, "on_behalf_of")
        # Only a person acts; a userset ("group:x#member") or wildcard cannot.
        if not v.startswith("user:") or "#" in v or v == "user:*":
            raise ValueError(f"on_behalf_of must be a single user, 'user:<sub>', got {v!r}")
        return v

    @model_validator(mode="after")
    def _relation_is_grantable(self):
        if not policy.is_grantable(self.relation, self.object):
            raise ValueError(
                f"relation {self.relation!r} on {self.object!r} cannot be granted through "
                "this API. Grantable: "
                + "; ".join(
                    f"{t}: {', '.join(sorted(rels))}"
                    for t, rels in sorted(policy.GRANTABLE_RELATIONS.items())
                )
            )
        return self


def _authorize_grant(request, payload: GrantIn) -> policy.Actor:
    try:
        actor = policy.resolve_actor(request.user, payload.on_behalf_of)
    except policy.Forbidden as exc:
        raise HttpError(403, str(exc)) from exc
    if not policy.can_manage_grants(actor, payload.object):
        raise HttpError(
            403, f"{actor.subject} may not manage roles on {payload.object}: needs can_administer."
        )
    return actor


def _apply(request, payload: GrantIn, action: GrantAudit.Action) -> None:
    """Authorize, then make the audited change (see `services.grants` for the
    audit-before-write ordering)."""
    actor = _authorize_grant(request, payload)
    grants.apply(
        action,
        fga.Relationship(user=payload.subject, relation=payload.relation, object=payload.object),
        performed_by=request.user,
        on_behalf_of=actor.subject if actor.delegate else "",
        reason=payload.reason,
    )


@router.post("/grants", response={201: None})
def create_grant(request, payload: GrantIn):
    _apply(request, payload, GrantAudit.Action.GRANT)
    return 201, None


@router.delete("/grants", response={204: None})
def revoke_grant(request, payload: GrantIn):
    _apply(request, payload, GrantAudit.Action.REVOKE)
    return 204, None
