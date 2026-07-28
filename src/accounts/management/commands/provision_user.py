from django.core.management.base import BaseCommand, CommandError

from accounts.models import User

_DEFAULT_IDP = "cognito"


class Command(BaseCommand):
    help = (
        "Create a user from their IdP subject claim, ahead of first login. "
        "This lets you write OpenFGA grants for a user before they have ever "
        "authenticated — the `sub` already exists in the IdP (Cognito assigns "
        "it at pool-user creation). See ADR 0003 and issue #4."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--sub",
            required=True,
            help="The IdP subject claim (e.g. from the Cognito console).",
        )
        parser.add_argument("--email", default="", help="Email address for the user.")
        parser.add_argument(
            "--identity-provider",
            default=_DEFAULT_IDP,
            help=f"Name of the IdP that issued --sub (default: {_DEFAULT_IDP})",
        )

    def handle(self, *args, **opts):
        username = opts["username"]
        sub = opts["sub"].strip()
        if not sub:
            raise CommandError("--sub must not be blank.")

        user = User.objects.filter(username=username).first()

        if user is None:
            clash = User.objects.filter(sub=sub).first()
            if clash is not None:
                raise CommandError(
                    f"sub {sub!r} already belongs to user {clash.username!r}. "
                    "A subject identifies exactly one principal."
                )
            user = User.objects.create(
                username=username,
                sub=sub,
                email=opts["email"],
                identity_provider=opts["identity_provider"],
            )
            self.stderr.write(f"Created user {username!r} with sub {sub!r}.")

        elif not user.sub:
            clash = User.objects.filter(sub=sub).first()
            if clash is not None:
                raise CommandError(
                    f"sub {sub!r} already belongs to user {clash.username!r}. "
                    "A subject identifies exactly one principal."
                )
            user.sub = sub
            fields = ["sub"]
            if opts["email"] and not user.email:
                user.email = opts["email"]
                fields.append("email")
            idp = opts["identity_provider"]
            if idp != _DEFAULT_IDP or not user.identity_provider:
                user.identity_provider = idp
                fields.append("identity_provider")
            user.save(update_fields=fields)
            self.stderr.write(f"Backfilled sub {sub!r} on existing user {username!r}.")

        elif sub != user.sub:
            raise CommandError(
                f"User {username!r} already has sub {user.sub!r}, which does not match "
                f"--sub {sub!r}. Refusing to repoint an existing subject: tuples already "
                "written against the old value would silently stop applying."
            )
        else:
            self.stderr.write(f"User {username!r} already has sub {sub!r}. Nothing to do.")

        self.stdout.write(f"user:{sub}")
