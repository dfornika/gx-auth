from django.conf import settings
from django.db import models


class GrantAudit(models.Model):
    """Append-only audit trail of grant/revoke operations performed through the
    control plane. OpenFGA holds the live tuples; this records who changed what,
    when, and why. See docs/003-integration-and-sync.md.
    """

    class Action(models.TextChoices):
        GRANT = "grant", "grant"
        REVOKE = "revoke", "revoke"

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
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.subject} {self.relation} {self.object}"
