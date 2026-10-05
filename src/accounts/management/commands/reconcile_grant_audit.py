from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from authz.models import GrantAudit
from authz.services import fga


class Command(BaseCommand):
    help = (
        "Settle GrantAudit rows left `pending` — a grant or revoke whose engine "
        "write was never confirmed (process died, or the status update failed). "
        "Reads the store and marks each row `applied` or `failed`. Rows "
        "superseded by a later change to the same tuple cannot be judged from "
        "the store, so they are reported and left for a human. See "
        "authz/services/grants.py."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-age",
            type=int,
            default=300,
            help="Only consider rows at least this many seconds old, so in-flight "
            "requests are not judged mid-write (default: 300).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Report without updating.")

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(seconds=opts["min_age"])
        pending = GrantAudit.objects.filter(
            status=GrantAudit.Status.PENDING, created_at__lte=cutoff
        ).order_by("created_at")

        settled = superseded = 0
        for audit in pending:
            label = f"#{audit.pk} {audit.action} {audit.subject} {audit.relation} {audit.object}"
            later = GrantAudit.objects.filter(
                subject=audit.subject,
                relation=audit.relation,
                object=audit.object,
                created_at__gt=audit.created_at,
            ).exists()
            if later:
                superseded += 1
                self.stdout.write(
                    self.style.WARNING(f"{label}: superseded by a later change; review by hand")
                )
                continue

            page = fga.read_tuples(user=audit.subject, relation=audit.relation, obj=audit.object)
            in_store = bool(page.tuples)
            took_effect = in_store == (audit.action == GrantAudit.Action.GRANT)
            status = GrantAudit.Status.APPLIED if took_effect else GrantAudit.Status.FAILED

            if not opts["dry_run"]:
                GrantAudit.objects.filter(pk=audit.pk, status=GrantAudit.Status.PENDING).update(
                    status=status
                )
            settled += 1
            self.stdout.write(f"{label}: tuple {'present' if in_store else 'absent'} -> {status}")

        verb = "would settle" if opts["dry_run"] else "settled"
        self.stdout.write(f"{verb} {settled}; {superseded} superseded, left pending")
