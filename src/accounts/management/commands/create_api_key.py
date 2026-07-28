from django.core.management.base import BaseCommand, CommandError

from accounts.models import APIKey, User

_DEFAULT_IDP = "cognito"


class Command(BaseCommand):
    help = (
        "Mint an API key for a user, creating the user if needed. "
        "Prints the raw key to stdout. Requires the user's IdP subject claim: an "
        "API key identifies a user, and a user is only meaningful to OpenFGA if it "
        "carries a `sub` — service accounts included. See ADR 0003."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--name", default="default", help="Label for the key")
        parser.add_argument(
            "--sub",
            default="",
            help=(
                "The IdP subject claim for this principal. Required when creating "
                "the user, or when an existing user has none."
            ),
        )
        parser.add_argument(
            "--identity-provider",
            default=_DEFAULT_IDP,
            help=f"Name of the IdP that issued --sub (default: {_DEFAULT_IDP})",
        )

    def handle(self, *args, **opts):
        username = opts["username"]
        sub = (opts["sub"] or "").strip()
        user = User.objects.filter(username=username).first()

        if user is None:
            # This command used to mint `svc-<username>` here. That is a locally
            # invented id: unique within this database and nowhere else, so two
            # services could both create `svc-catalog` and silently share access
            # in the shared store. Service accounts are provisioned at the IdP
            # like every other principal (Cognito app client / Entra app
            # registration) and carry a real sub.
            if not sub:
                raise CommandError(
                    f"No user {username!r} exists, and --sub was not given.\n"
                    "Every principal needs the subject claim its IdP issued — service "
                    "accounts too. Provision one as a Cognito app client (or Entra app "
                    "registration) and pass its sub:\n"
                    f"    ... create_api_key {username} --sub <sub-from-idp>\n"
                    "A locally-invented sub collides across services in the shared "
                    "store; see ADR 0003."
                )
            clash = User.objects.filter(sub=sub).first()
            if clash is not None:
                raise CommandError(
                    f"sub {sub!r} already belongs to user {clash.username!r}. "
                    "A subject identifies exactly one principal."
                )
            user = User.objects.create(
                username=username, sub=sub, identity_provider=opts["identity_provider"]
            )
            self.stderr.write(f"Created user {username!r} with sub {sub!r}.")

        elif not user.sub:
            # Backfilling a blank sub is the one identity change allowed here:
            # it fills a hole rather than repointing an existing subject, and
            # any tuples written for this user would have had no subject to key.
            if not sub:
                raise CommandError(
                    f"User {username!r} has no `sub`, so it has no OpenFGA subject and "
                    "a key for it could not authorize anything. Pass --sub to backfill "
                    "the value from the IdP."
                )
            clash = User.objects.filter(sub=sub).first()
            if clash is not None:
                raise CommandError(
                    f"sub {sub!r} already belongs to user {clash.username!r}. "
                    "A subject identifies exactly one principal."
                )
            user.sub = sub
            fields = ["sub"]
            idp = opts["identity_provider"]
            if idp != _DEFAULT_IDP or not user.identity_provider:
                user.identity_provider = idp
                fields.append("identity_provider")
            user.save(update_fields=fields)
            self.stderr.write(f"Backfilled sub {sub!r} on existing user {username!r}.")

        elif sub and sub != user.sub:
            raise CommandError(
                f"User {username!r} already has sub {user.sub!r}, which does not match "
                f"--sub {sub!r}. Refusing to repoint an existing subject: tuples already "
                "written against the old value would silently stop applying. Fix the "
                "identity deliberately if that is really what you want."
            )

        _, raw_key = APIKey.generate(user=user, name=opts["name"])
        # Print ONLY the raw key on stdout so callers can capture it:
        # KEY=$(... create_api_key svc --sub ...)
        self.stdout.write(raw_key)
