"""Create the OpenFGA database on the shared Postgres instance if it's absent.

Used at deploy time: gx-auth's own database is created by RDS, but the second
(openfga) database on the same instance has to be created explicitly before
`openfga migrate` can run. Idempotent.
"""

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the OpenFGA database on the same Postgres instance if it doesn't exist."

    def handle(self, *args, **options):
        name = settings.OPENFGA_DB_NAME
        db = settings.DATABASES["default"]
        # Connect to the 'postgres' maintenance database — CREATE DATABASE cannot
        # run inside a transaction, so use autocommit.
        conn = psycopg.connect(
            host=db["HOST"],
            port=db["PORT"],
            user=db["USER"],
            password=db["PASSWORD"],
            dbname="postgres",
            autocommit=True,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
                if cur.fetchone():
                    self.stdout.write(f"database '{name}' already exists")
                else:
                    # identifier can't be parameterized; name comes from settings, not user input
                    cur.execute(f'CREATE DATABASE "{name}"')
                    self.stdout.write(self.style.SUCCESS(f"created database '{name}'"))
        finally:
            conn.close()
