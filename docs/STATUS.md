# Where this is up to — 2026-07-24

Working notes for picking the OpenFGA inspector work back up. Not a design doc;
delete it once the branch merges and the follow-ups have homes.

## Done

Branch `feat/fga-admin-inspector` (commit `a02ae3f`), pushed, no PR opened yet.
49 tests pass, ruff clean, all three pages verified against a live store.

Three superuser-only read-only pages, hosted in the admin:

| page | shows |
|---|---|
| `/admin/fga/tuples/` | live tuples, filterable, paginated, with a scan fallback |
| `/admin/fga/expand/` | why an `object#relation` resolves, down to the users |
| `/admin/fga/tree/` | the `parent` hierarchy that roles inherit down |

Reachable from the `GrantAudit` changelist, which now carries three links.

The commit message is the detailed record — it documents every OpenFGA
behaviour discovered while building this (Read's filter rules, the mutated
options dict, blank-vs-None filters, Expand not resolving through
tuple-to-userset, urllib3 errors escaping the SDK). Read it with
`git show a02ae3f --stat` or `git log -1`.

**This completes the approved plan.** Everything below was explicitly deferred,
not left unfinished.

## Not done — inspector follow-ups

- **Orphaned-tuple check** (new; probably do this first). After any model change,
  answer "which stored tuples reference types or relations the active model no
  longer defines?" Those tuples still exist and still read, but any access they
  granted is silently gone. The classification logic already exists as a
  throwaway script from this session; it is a small page.
- **Model viewer.** `fga.read_model()` already returns what it needs. Would also
  enable a store-model vs `fga/model.json` drift check.
- **Check / list-objects sandbox.** Forms over the existing `fga.check()` and
  `fga.list_objects()`. Label it loudly so it is not mistaken for a write UI.
- **GrantAudit vs live-tuple drift.** Caveat that matters: only *role* grants go
  through the audited path, so a naive diff flags every structural `parent` /
  `project` tuple as unaudited and buries the real signal. Needs a relation
  allowlist and a third "structural — not audited by design" bucket.

## Not done — wider open questions (predate this work)

- **`ListObjects` performance at realistic scale.** `docs/003` calls it the #1
  ReBAC gotcha and says to prototype it early; still untested against real
  per-project sample counts. Needs no AWS. Highest-value experiment available.
- **Tuple-sync strategy.** `docs/003` recommends write-through, but gx-poc has
  settled informally on a hybrid — role grants audited through the control
  plane, structural edges written straight to OpenFGA. If that hybrid is the
  intended endpoint, the "all writes go through gx-auth" rule in `CLAUDE.md`
  needs rewording.
- **OpenFGA has no authn configured.** Anything with network reach can `Write`,
  not only `Check`, which undercuts the audit story given consumers are meant to
  call the engine directly on the hot path.
- **Pin the OpenFGA image.** `compose.yml` uses `openfga/openfga:latest` for both
  services, so server behaviour can change under you on any `docker compose pull`.
- **AWS deployment.** `infrastructure/` (TypeScript CDK) is still untracked and
  never deployed; the plan is a Python CDK rewrite against the existing work dev
  environment. Its real value is the bootstrap runbook, not the constructs. Note
  it puts both databases on one RDS instance, unlike local dev's two containers.

## Environment gotchas

- **`.env` is gitignored**, so `FGA_STORE_ID` / `FGA_MODEL_ID` do not travel
  between machines. Leave `FGA_MODEL_ID` blank to track the store's latest model
   — a stale pin here meant gx-auth was answering against a superseded 12-type
  model while `model.fga` on disk was the 4-type one. The inspector's status
  strip now warns about this.
- **Two Postgres containers locally:** `db` holds `gxauth` (Django, managed by
  `just migrate`), `openfga-db` holds `openfga` (OpenFGA's own schema, managed by
  its `migrate` command via the `openfga-migrate` compose service). Tuples are
  rows in the `tuple` table there. Never write to it directly with SQL — that
  bypasses model validation.
- **Model changes never migrate existing tuples.** Removing a *type* silently
  makes dependent access evaporate while the tuples remain; removing a
  *relation* makes checks fail loudly with a 400. Derived relations (`can_*`)
  have no tuples behind them and are free to change; storable relations
  (`admin`, `member`, `viewer`, `parent`, `project`) are a data migration.
