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
config/            Django project (settings, urls, wsgi/asgi)
accounts/          User (OIDC sub), API keys, OIDC backend
authz/             control plane: OpenFGA wrapper, check/list/grant API, audit
  services/fga.py  the single integration point with OpenFGA
fga/model.fga      the authorization model (see docs/002)
compose.yml        db + openfga + openfga-db + web + utility
```

## Status

Scaffold. Not yet run end-to-end — `just bootstrap` will generate `uv.lock` and
pull dependencies on first use. The OpenFGA SDK call surface in
`authz/services/fga.py` should be confirmed against the pinned version.
