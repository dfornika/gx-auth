# Status

Where gx-auth stands, and what is open. Update this file as items close; it
replaces the July 2026 working notes, which are in git history.

## Built

- **Model.** Projects with nested inheritance; samples and analysis outputs
  inheriting from their project; a `platform` type for control-plane roles.
  Covered by offline model tests (doc 002).
- **Control-plane API.** `check`, `list-objects`, and audited `grants`. The
  API authorizes its own callers: an actor needs `can_administer` to change a
  role, and delegates may act for end users (ADR 0004).
- **Audit.** Every grant and revoke is recorded before it is applied;
  `reconcile_grant_audit` settles rows whose outcome is unknown (doc 003).
- **Identity.** OIDC login (Cognito), API keys, the `user:<sub>` subject
  contract, and `provision_user` for users who have not signed in yet (doc
  004).
- **Admin inspector.** Read-only pages for live tuples (`/admin/fga/tuples/`),
  why a relation resolves (`/admin/fga/expand/`) and the project tree
  (`/admin/fga/tree/`).
- **SDK** (`sdk/`, 0.2.0). `check`, `list_objects`, tuple writes, audited
  `grant`/`revoke` with `on_behalf_of`, id validation, and a Cognito JWT
  authenticator.
- **First consumer.** sequence-data-submission-service answers per-project
  checks from OpenFGA when `AUTHZ_BACKEND=gxauth`. It is read-only so far:
  its role changes still go to its local store.

## Open, roughly by priority

1. **Who owns "project"?** One id space is shared by every service. Decide
   whether a project spans services (and who issues its id), or whether ids
   need namespacing so separate projects cannot collide. This blocks a second
   consumer.
2. **OpenFGA has no authentication.** Anything with network access can write
   tuples, which bypasses the control plane and its audit log. Fix this before
   services call the engine directly anywhere but a developer's machine.
3. **Structural tuples have no write path.** Nothing writes `parent` or
   `project` edges when services create resources. Choose write-through,
   outbox or events (doc 003).
4. **General reconciliation.** Compare each service's resources with the
   store, and the audit log with live tuples. Only role grants are audited, so
   structural tuples need a separate "not audited by design" category, or
   every one of them will show as drift.
5. **`ListObjects` at realistic volume.** Not yet measured. It needs no cloud
   resources and decides whether resource-level tuples are viable.
6. **Token handling** (doc 004). The SDK accepts only ID tokens, which shuts
   out machine-to-machine clients, and SDS's own bearer validation is too
   loose.
7. **Hot-path timeouts.** The SDK uses the OpenFGA client's defaults (minutes,
   with retries) and a new client per call. An engine outage would hang
   request workers instead of failing closed quickly.
8. **Service-specific permissions.** `can_create` means "submit sequences" in
   SDS, and would mean something else elsewhere. Consider permissions named
   per service, derived from the shared roles.
9. **Deployment.** No cloud deployment yet. Pin the OpenFGA image: `compose.yml`
   uses `openfga/openfga:latest`.

### Inspector follow-ups

- **Orphaned tuples.** List stored tuples whose type or relation the active
  model no longer defines. Their access is silently gone. Probably first.
- **Model viewer**, with a check for drift between the store's model and
  `fga/model.json`.
- **Check / list-objects sandbox.** Forms over the existing functions,
  clearly marked as read-only.

## Environment gotchas

- **`.env` is gitignored**, so `FGA_STORE_ID` and `FGA_MODEL_ID` do not travel
  between machines. Leave `FGA_MODEL_ID` blank to follow the store's latest
  model; a stale pin silently answers against an old model. The inspector
  warns when this happens.
- **Two Postgres databases locally.** `db` holds gx-auth's Django data;
  `openfga-db` holds OpenFGA's. Never edit OpenFGA's tables with SQL, which
  bypasses model validation.
- **Editing `.env` needs a container recreate** (`just reload <service>`).
  `docker compose restart` keeps the old environment.
