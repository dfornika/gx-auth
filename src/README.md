# gx-auth

A genomics authorization service

## Stack

- Django + django-ninja (API), uv-managed, `config/` project package
- OpenFGA (ReBAC decision engine), Postgres datastore
- mozilla-django-oidc for Cognito/Entra login (identity only)

## Quick start

```shell
just bootstrap          # .env + uv.lock + build images
just up                 # start db, openfga (+ its db), web
just migrate            # apply Django migrations
just fga-store-create   # create a store; put the printed id in .env as FGA_STORE_ID
just reload web         # recreate web so it reads FGA_STORE_ID (restart does NOT reload .env!)
just fga-model-write    # load fga/model.fga into the store
just fga-seed           # optional: load the demo tuples (fga/seed.tuples.csv)
just createsuperuser
```

> **Gotcha:** editing `.env` requires recreating the affected container
> (`just reload <service>`). `docker compose restart` reuses the old
> environment, so a freshly-set `FGA_STORE_ID` won't be seen and OpenFGA calls
> fail with "store_id is required but not configured".

API docs: http://localhost:8000/api/docs

Inspect OpenFGA with the `fga` CLI (the built-in playground is deprecated and
not exposed): `just fga-check`, `just fga-tuple-write`, `just fga-model-list`.

## Layout

```
config/                  Django project (settings, urls, wsgi/asgi)
accounts/                User (IdP `sub`), API keys, OIDC backend, management commands
authz/
  api.py                 check / list-objects / grants endpoints
  policy.py              who may call the control plane (ADR 0004)
  services/fga.py        the single integration point with OpenFGA
  services/grants.py     audited grant/revoke: audit row first, then the engine
  services/inspector.py  read-only store inspector behind /admin/fga/
fga/                     model.fga, its compiled model.json, model tests, demo tuples
compose.yml              db, openfga, openfga-db, web, utility
```

## Operating it

```shell
just manage grant_platform_role admin <sub>      # an operator: may manage any project's roles
just manage grant_platform_role delegate <sub>   # a service allowed to act for end users
just manage provision_user <username> --sub <sub>
just manage create_api_key <username> --sub <sub>
just manage reconcile_grant_audit [--dry-run]    # settle audit rows left pending
```

## Tests

```shell
just test                # Django tests (fake OpenFGA client, real Postgres)
just fga-model-test      # model decisions, offline
```
