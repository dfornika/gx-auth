# gx-auth — notes for Claude

An experimental shared authorization service for cloud-based genomics systems: Django Ninja control plane over
an OpenFGA (ReBAC) decision engine.

## Read first

`docs/` holds the design. `docs/001` (architecture), `docs/002` (the OpenFGA
model), `docs/003` (integration & the hard tuple-sync problem), `docs/004`
(identity/tokens). ADRs in `docs/decisions/`.

## Conventions

- **uv** for deps (`src/pyproject.toml`, `[tool.uv] package = false`); **not** pip/poetry.
- `src/` layout; Django project package is `config/`; `config/__init__.py` holds `__version__` (CalVer).
- **`just`** task runner — `just up`, `just manage <cmd>`, `just test`, `just migrate`.
- Config via **environs** (`env.str/bool/dj_db_url`). Settings in `config/settings.py`.
- API via **django-ninja**; per-app `Router`s composed in `config/urls.py`.
- Login via **mozilla-django-oidc** (`accounts/oidc.py`), Cognito today. Tokens are identity-only.
- Admin via **django-unfold**. Lint/format via **ruff**. Tests via **pytest** (`just test`).

## Architectural rules (do not violate)

- **No authorization in the IdP.** Never use Cognito groups / Pre-Token Lambda
  (or Entra claims) to carry permissions. Token = identity only. (ADR 0002)
- **OpenFGA is the engine; gx-auth is the control plane.** Don't reimplement
  decision logic in Python. All engine calls go through `authz/services/fga.py`.
- **Engine stays swappable** (SpiceDB is the fallback) — keep the wrapper thin.
- Model authoring uses the **`fga` CLI** (`just fga-model-*`), not the Python SDK.

## Key files

- `authz/services/fga.py` — the single OpenFGA integration point.
- `src/fga/model.fga` — the authorization model (explained in `docs/002`).
- `authz/api.py` — check / list-objects / audited grants.
- `accounts/` — User (`sub`), API keys, OIDC backend.
