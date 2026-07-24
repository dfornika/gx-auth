from django.core.management.base import BaseCommand

from accounts.models import APIKey, User


class Command(BaseCommand):
    help = "Create (or reuse) a user and mint an API key. Prints the raw key to stdout."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--name", default="default", help="Label for the key")

    def handle(self, *args, **opts):
        user, _ = User.objects.get_or_create(
            username=opts["username"],
            defaults={"sub": f"svc-{opts['username']}", "identity_provider": "service-account"},
        )
        _, raw_key = APIKey.generate(user=user, name=opts["name"])
        # Print ONLY the raw key so callers can capture it: KEY=$(... create_api_key svc)
        self.stdout.write(raw_key)
