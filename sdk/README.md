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

## Use

```python
import gx_auth_sdk as authz
from gx_auth_sdk import require, StubHeaderAuth

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
- `config.py` — env/explicit configuration

It carries **no policy**: the authorization model and object-id conventions live
in gx-auth and each service, not here.
