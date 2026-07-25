"""Ensure an OpenFGA store exists and the current model is written to it.

Deployed environments can't use the local "create store, paste the id into .env"
flow, so this command does it programmatically against the OpenFGA HTTP API:

- If FGA_STORE_ID is set (and not the 'PENDING' placeholder), reuse that store.
- Otherwise create a store named 'gx-auth' and use its id.
- Write the model from fga/model.json (the compiled form of fga/model.fga).
- Print `FGA_STORE_ID=<id>` so the deploy runbook can capture it into SSM.

Idempotent: re-running against an existing store just writes a fresh (identical)
model version. Uses stdlib urllib so it needs no extra dependency; assumes the
OpenFGA instance has authentication disabled (the internal default here).
"""

import json
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


class Command(BaseCommand):
    help = "Create/reuse an OpenFGA store and write the current model. Prints FGA_STORE_ID."

    def add_arguments(self, parser):
        parser.add_argument("--store-name", default="gx-auth")

    def handle(self, *args, **options):
        api = settings.FGA_API_URL.rstrip("/")
        store_id = settings.FGA_STORE_ID
        if store_id == "PENDING":
            store_id = ""

        if not store_id:
            store_id = _post(f"{api}/stores", {"name": options["store_name"]})["id"]
            self.stdout.write(f"created store '{options['store_name']}' -> {store_id}")
        else:
            self.stdout.write(f"reusing store {store_id}")

        model = json.loads(Path(settings.BASE_DIR, "fga", "model.json").read_text())
        resp = _post(f"{api}/stores/{store_id}/authorization-models", model)

        self.stdout.write(
            self.style.SUCCESS(f"wrote authorization model {resp['authorization_model_id']}")
        )
        # Machine-readable last line for the runbook to capture.
        self.stdout.write(f"FGA_STORE_ID={store_id}")
