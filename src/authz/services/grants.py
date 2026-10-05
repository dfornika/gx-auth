"""Audited tuple writes: the one path that changes role tuples in the store.

Used by the grants API and the `grant_platform_role` command. The ordering is
the point of this module:

1. Commit a `GrantAudit` row as `pending`.
2. Write (or delete) the tuple in OpenFGA.
3. Mark the row `applied`, or `failed` if the engine refused or errored.

The engine cannot join a database transaction, so a change is never atomic
across the two stores. This ordering at least guarantees that **no change
reaches the store without a committed audit row**. If the process dies after
step 1, or step 3's update fails, the row stays `pending`: the outcome is
unknown, but it is recorded and detectable. `reconcile_grant_audit` resolves it
by reading the store.
"""

from __future__ import annotations

import logging

from django.db import transaction

from authz.models import GrantAudit

from . import fga

logger = logging.getLogger(__name__)


def apply(
    action: GrantAudit.Action,
    rel: fga.Relationship,
    *,
    performed_by=None,
    on_behalf_of: str = "",
    reason: str = "",
) -> GrantAudit:
    """Audit, then apply, one grant or revoke. Re-raises an engine error after
    recording the attempt as `failed`."""
    # Its own transaction, committed before the engine is touched, even if a
    # caller has one open: the row must exist whatever happens next.
    with transaction.atomic(durable=True):
        audit = GrantAudit.objects.create(
            action=action,
            subject=rel.user,
            relation=rel.relation,
            object=rel.object,
            performed_by=performed_by,
            on_behalf_of=on_behalf_of,
            reason=reason,
        )

    try:
        if action == GrantAudit.Action.GRANT:
            fga.write_tuple(rel)
        else:
            fga.delete_tuple(rel)
    except Exception:
        _set_status(audit, GrantAudit.Status.FAILED)
        raise

    _set_status(audit, GrantAudit.Status.APPLIED)
    return audit


def _set_status(audit: GrantAudit, status: GrantAudit.Status) -> None:
    """Best effort: if this update fails the row stays `pending`, which the
    reconciliation command exists to resolve. Never mask the engine outcome."""
    try:
        GrantAudit.objects.filter(pk=audit.pk).update(status=status)
        audit.status = status
    except Exception:
        logger.exception(
            "GrantAudit %s: could not record status %r; left pending for reconcile_grant_audit",
            audit.pk,
            status,
        )
