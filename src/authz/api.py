"""Authorization control-plane API.

- `check` / `list-objects`: thin, audited wrappers over the OpenFGA engine, for
  callers that prefer a domain API. Hot-path callers may also hit OpenFGA
  directly (see docs/001).
- `grants`: the audited write path — domain grant/revoke that translates into
  tuple writes and records a GrantAudit row (see docs/003).
"""

from ninja import Router, Schema

from .models import GrantAudit
from .services import fga

router = Router(tags=["authz"])


# --- Check -----------------------------------------------------------------


class CheckIn(Schema):
    user: str  # e.g. "user:abc"
    relation: str  # e.g. "can_view"
    object: str  # e.g. "sample:42"
    context: dict | None = None  # condition params, e.g. {"required_level": 3}


class CheckOut(Schema):
    allowed: bool


@router.post("/check", response=CheckOut)
def check(request, payload: CheckIn):
    allowed = fga.check(
        payload.user, payload.relation, payload.object, context=payload.context
    )
    return {"allowed": allowed}


# --- List objects ----------------------------------------------------------


class ListObjectsIn(Schema):
    user: str
    relation: str
    type: str  # object type, e.g. "sample"
    context: dict | None = None


class ListObjectsOut(Schema):
    objects: list[str]


@router.post("/list-objects", response=ListObjectsOut)
def list_objects(request, payload: ListObjectsIn):
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


@router.post("/grants", response={201: None})
def create_grant(request, payload: GrantIn):
    rel = fga.Relationship(user=payload.subject, relation=payload.relation, object=payload.object)
    fga.write_tuple(rel)
    GrantAudit.objects.create(
        action=GrantAudit.Action.GRANT,
        subject=payload.subject,
        relation=payload.relation,
        object=payload.object,
        performed_by=request.user,
        reason=payload.reason,
    )
    return 201, None


@router.delete("/grants", response={204: None})
def revoke_grant(request, payload: GrantIn):
    rel = fga.Relationship(user=payload.subject, relation=payload.relation, object=payload.object)
    fga.delete_tuple(rel)
    GrantAudit.objects.create(
        action=GrantAudit.Action.REVOKE,
        subject=payload.subject,
        relation=payload.relation,
        object=payload.object,
        performed_by=request.user,
        reason=payload.reason,
    )
    return 204, None
