from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from authz import policy
from authz.models import GrantAudit
from authz.services import fga

_ROLES = ("admin", "delegate")


class Command(BaseCommand):
    help = (
        "Grant (or --revoke) a platform role: `admin` (may manage role grants on "
        "any project) or `delegate` (a service trusted to act on behalf of end "
        "users). These are deliberately not grantable over the HTTP API, so this "
        "operator command is the only way in. Recorded in GrantAudit with no "
        "performed_by. See ADR 0004."
    )

    def add_arguments(self, parser):
        parser.add_argument("role", choices=_ROLES)
        parser.add_argument(
            "sub",
            help="The principal's IdP subject claim (for a service, its Cognito app client id).",
        )
        parser.add_argument("--reason", default="", help="Recorded in the audit log.")
        parser.add_argument("--revoke", action="store_true", help="Remove the role instead.")

    def handle(self, *args, **opts):
        sub = opts["sub"].strip()
        if not sub or ":" in sub or any(c.isspace() for c in sub):
            raise CommandError(
                f"Expected a bare IdP sub (e.g. 'a1b2c3…'), got {opts['sub']!r}. "
                "The `user:` prefix is added for you."
            )
        subject = f"user:{sub}"
        obj = policy.platform_object()
        action = GrantAudit.Action.REVOKE if opts["revoke"] else GrantAudit.Action.GRANT
        rel = fga.Relationship(user=subject, relation=opts["role"], object=obj)

        # Same ordering as the grants API: a failed engine write rolls the
        # audit row back.
        with transaction.atomic():
            GrantAudit.objects.create(
                action=action,
                subject=subject,
                relation=opts["role"],
                object=obj,
                performed_by=None,
                reason=opts["reason"] or f"grant_platform_role ({action})",
            )
            if action == GrantAudit.Action.GRANT:
                fga.write_tuple(rel)
            else:
                fga.delete_tuple(rel)

        self.stdout.write(f"{action} {subject} {opts['role']} {obj}")
