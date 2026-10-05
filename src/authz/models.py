from django.conf import settings
from django.db import models


class GrantAudit(models.Model):
    """Append-only audit trail of grant/revoke operations performed through the
    control plane. OpenFGA holds the live tuples; this records who changed what,
    when, and why. See docs/003-integration-and-sync.md.

    Rows are never edited except for `status`, which moves once from `pending`
    to `applied` or `failed`. The row is committed *before* the engine write
    (`authz.services.grants`), so a change can never reach the store without a
    row. A row left `pending` means the outcome is unknown, and
    `reconcile_grant_audit` settles it against the store.
    """

    class Action(models.TextChoices):
        GRANT = "grant", "grant"
        REVOKE = "revoke", "revoke"

    class Status(models.TextChoices):
        PENDING = "pending", "pending"  # committed; engine write not yet confirmed
        APPLIED = "applied", "applied"  # the store reflects this change
        FAILED = "failed", "failed"  # the engine write did not happen

    action = models.CharField(max_length=8, choices=Action.choices)

    # The relationship tuple, as fully-qualified FGA ids.
    subject = models.CharField(max_length=255)  # e.g. user:abc, group:lab-x#member
    relation = models.CharField(max_length=64)  # e.g. member, viewer
    object = models.CharField(max_length=255)  # e.g. project:42

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="grant_audits",
    )
    # Set when a platform delegate (a consuming service, recorded as
    # `performed_by`) acted for an end user: the subject whose authority the
    # grant was checked against. Blank when the caller acted for itself.
    on_behalf_of = models.CharField(max_length=255, blank=True, default="")
    reason = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.subject} {self.relation} {self.object}"
