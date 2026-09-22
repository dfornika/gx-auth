"""gx-auth control-plane client (audited role grants over HTTP)."""

from __future__ import annotations

import httpx

from .config import get_config
from .ids import validate_object, validate_subject


def _post(
    method: str,
    subject: str,
    relation: str,
    obj: str,
    reason: str,
    on_behalf_of: str | None,
    *,
    verb: str,
) -> None:
    validate_subject(subject, f"{verb} subject")
    validate_object(obj, f"{verb} object")
    body = {"subject": subject, "relation": relation, "object": obj, "reason": reason}
    if on_behalf_of is not None:
        validate_subject(on_behalf_of, f"{verb} on_behalf_of")
        body["on_behalf_of"] = on_behalf_of
    cfg = get_config()
    resp = httpx.request(
        method,
        f"{cfg.control_plane_url}/api/authz/grants",
        headers={"Authorization": f"Bearer {cfg.control_plane_api_key}"},
        json=body,
        timeout=10.0,
    )
    resp.raise_for_status()


def grant(
    subject: str, relation: str, obj: str, reason: str = "", *, on_behalf_of: str | None = None
) -> None:
    """Grant `relation` on `obj` to `subject` (audited by gx-auth).

    gx-auth allows it only if the actor holds `can_administer` on `obj`. The
    actor is this service's own principal unless `on_behalf_of` names the end
    user it acts for (e.g. `"user:<sub>"` of whoever clicked "add member") —
    which requires this service to be a platform delegate. See gx-auth ADR 0004.
    """
    _post("POST", subject, relation, obj, reason, on_behalf_of, verb="grant")


def revoke(
    subject: str, relation: str, obj: str, reason: str = "", *, on_behalf_of: str | None = None
) -> None:
    """Revoke `relation` on `obj` from `subject` (audited by gx-auth).

    Authorized exactly like `grant`, including `on_behalf_of`.
    """
    _post("DELETE", subject, relation, obj, reason, on_behalf_of, verb="revoke")
