# gx-auth-sdk

Consumer SDK for the [`gx-auth`](../) authorization plane. A service imports this
to enforce authorization: it talks to **OpenFGA** for decisions (the hot path)
and to the **gx-auth control plane** for audited grants.

It lives in the gx-auth repo (under `sdk/`) but is a **separate, independently
published package** — it must never import gx-auth's service code (`../src`).

## Install

Install from the repo subdirectory, pinned to a tag:

```toml
# pyproject.toml
dependencies = ["gx-auth-sdk[ninja]"]

[tool.uv.sources]
gx-auth-sdk = { git = "https://github.com/…/gx-auth.git", subdirectory = "sdk", tag = "sdk-v0.1.0" }
```

For local development against a checkout, use a path instead:

```toml
[tool.uv.sources]
gx-auth-sdk = { path = "../gx-auth/sdk", editable = true }
```

Because it shares the repo with the service, release it under a **prefixed tag**
(e.g. `sdk-v0.1.0`) so the SDK's versions stay independent of gx-auth's, and
consumers pin `tag=…, subdirectory=sdk`.

## Configure

Reads these environment variables (load your `.env` first):

| var | meaning | default |
|---|---|---|
| `FGA_API_URL` | OpenFGA HTTP endpoint | `http://localhost:8080` |
| `FGA_STORE_ID` | OpenFGA store id | *(required)* |
| `GXAUTH_URL` | gx-auth control-plane base url | `http://localhost:8000` |
| `GXAUTH_API_KEY` | service-account key for the control plane | `""` |

Or call `gx_auth_sdk.configure(fga_store_id=..., ...)` explicitly.

### Django

`environs`/`django-environ` load `.env` into Django **settings**, not
`os.environ`, so the env-var path above won't see them. Wire the SDK from your
app's `AppConfig.ready()` instead:

```python
class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        from django.conf import settings
        import gx_auth_sdk
        gx_auth_sdk.configure(
            fga_api_url=settings.FGA_API_URL,
            fga_store_id=settings.FGA_STORE_ID,
            control_plane_url=settings.GXAUTH_URL,
            control_plane_api_key=settings.GXAUTH_API_KEY,
        )
```

### Import ordering

`import gx_auth_sdk` is safe anywhere — the core is framework-agnostic and pulls
in nothing but `openfga-sdk` and `httpx`.

`require` and `StubHeaderAuth` are different: they import django-ninja, which
evaluates its pydantic settings model at import time and so needs Django
settings to already be loaded. They are resolved lazily, on first attribute
access, so reach for them **after `django.setup()`** — from a views/api module,
`AppConfig.ready()`, or inside a function. Naming them at module scope in
`settings.py` raises an `ImportError` that says so.

## Use

```python
import gx_auth_sdk as authz
from gx_auth_sdk import require, StubHeaderAuth  # in an app module, not settings.py

# enforce (django-ninja):
@router.post("/projects/{pid}/samples")
@require("can_edit", "project:{pid}")
def create_sample(request, pid: int, payload): ...

# reads:
authz.check("user:anne", "can_view", "sample:1")          # -> bool
authz.list_objects("user:anne", "can_view", "sample")     # -> ["sample:1", ...]

# resource tuples (service-owned):
authz.write_relationship("project:1", "project", "sample:1")

# audited grants (control plane):
authz.grant("user:anne", "viewer", "project:1", reason="shared")
authz.revoke("user:anne", "viewer", "project:1")
```

## Layout

- `client.py` — OpenFGA wrapper (framework-agnostic)
- `control_plane.py` — gx-auth HTTP client (framework-agnostic)
- `ninja.py` — `require()` decorator (needs the `ninja` extra)
- `identity.py` — `StubHeaderAuth` for dev; real OIDC JWT auth belongs here later
- `ids.py` — shallow validation of `type:id` ids (see below)
- `config.py` — env/explicit configuration

It carries **no policy**: the authorization model and object-id conventions live
in gx-auth and each service, not here.

## Malformed ids raise, they do not deny

Every call validates its ids and raises `ValueError` on one that is obviously
malformed — a missing or empty half (`"user:"`, `"project:"`), a bare name with
no type (`"alice"`), embedded whitespace.

This is deliberate. OpenFGA answers a malformed Check with `allowed: false`,
which is indistinguishable from a legitimate denial, so a data bug would surface
as a permissions problem — for one user, at the point of use. The canonical case
is an account with **no IdP `sub`**, whose subject renders as `"user:"`.

Validation is shallow by design: wrongly rejecting a valid id is worse than
passing an odd one through, so the engine stays the authority on its own grammar.
Usersets (`group:lab-x#member`) and wildcards (`user:*`) are valid subjects but
not valid objects.

A caller that wants a denial rather than an exception should check for the
condition itself — an account with no subject has no authorization, and that is a
decision the service should make explicitly:

```python
if not user.sub:
    logger.error("user %s has no sub, so no OpenFGA subject; denying", user.pk)
    return False
return authz.check(f"user:{user.sub}", "can_view", f"project:{pid}")
```
