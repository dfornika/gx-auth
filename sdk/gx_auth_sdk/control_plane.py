"""gx-auth control-plane client (audited role grants over HTTP)."""

from __future__ import annotations

import httpx

from .config import get_config


def _post(method: str, subject: str, relation: str, obj: str, reason: str) -> None:
    cfg = get_config()
    resp = httpx.request(
        method,
        f"{cfg.control_plane_url}/api/authz/grants",
        headers={"Authorization": f"Bearer {cfg.control_plane_api_key}"},
        json={"subject": subject, "relation": relation, "object": obj, "reason": reason},
        timeout=10.0,
    )
    resp.raise_for_status()


def grant(subject: str, relation: str, obj: str, reason: str = "") -> None:
    """Grant `relation` on `obj` to `subject` (audited by gx-auth)."""
    _post("POST", subject, relation, obj, reason)


def revoke(subject: str, relation: str, obj: str, reason: str = "") -> None:
    """Revoke `relation` on `obj` from `subject` (audited by gx-auth)."""
    _post("DELETE", subject, relation, obj, reason)
