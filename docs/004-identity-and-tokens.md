# 004 — Identity & tokens

## Authentication stays with the cloud IdP

`gx-auth` does no authentication. Users log in against **AWS Cognito** (today),
and each service validates the resulting OIDC token itself — exactly as GX Core
already does with `mozilla-django-oidc` and a `CognitoOIDCBackend`. `gx-auth`
consumes the same identity: the token's `sub` claim is the subject id it uses in
OpenFGA (`user:<sub>`).

Both Cognito and Entra expose standard OIDC discovery, so to `gx-auth` and its
sibling services an IdP is just a set of endpoints + a JWKS URI.

## The "thin token" discipline (this is load-bearing)

**Put no authorization in the token, and none in the IdP.** Specifically:

- Do **not** use `cognito:groups` (or an Entra `roles`/`groups` claim) to carry
  permissions.
- Do **not** use a Cognito Pre-Token-Generation Lambda (or Entra claims-mapping
  policy) to inject permissions.

The token carries **identity only**: `sub`, `email`, and at most a coarse role
(e.g. platform-admin vs. ordinary user). All fine-grained authorization is
answered at request time by OpenFGA via `gx-auth`.

This one rule does double duty:

1. **It preserves the Azure pivot.** If permissions never live in Cognito, then
   swapping Cognito for Entra is a configuration change (new issuer, JWKS,
   endpoints) — not a re-modelling of your authorization. Both are "just an OIDC
   issuer" to your services.
2. **It gives you the expressive authorization you wanted.** Group-claim/Lambda
   authorization is coarse and IdP-locked — the very thing this project exists to
   escape. Keeping authz in OpenFGA is what makes hierarchy, sharing, and
   conditions possible.

See [ADR 0002](./decisions/0002-cloud-neutral-identity.md).

## Three credential types to plan for

Do not assume one token type. The platform needs:

1. **Interactive user tokens** — OIDC login via Cognito/Entra. `sub` → `user:<sub>`.
2. **Service-account / machine-to-machine tokens** — for services calling each
   other and for automation. Cognito app clients (`client_credentials`) and Entra
   app registrations both cover this natively. A service account is an IdP
   principal like any other: it is registered at the IdP, carries a real `sub`,
   and is an ordinary `user:<sub>` subject — **not** a locally-minted id and not
   a separate OpenFGA type. See [ADR 0003](./decisions/0003-idp-sub-is-the-only-subject.md).
3. **Long-lived, user-scoped API keys** — issued by the platform for scripts/CLI
   use, always a subset of the owner's access. GX Core already has an `APIKey`
   model + `BearerTokenAuth`; `gx-auth` mirrors that pattern so keys can
   authenticate to the control-plane API. The key identifies the user; OpenFGA
   still makes the decision.

## Mapping IdP identity to OpenFGA subjects

- The stable subject is the OIDC `sub`. Store it on the local `User` record
  (as GX Core does: `User.sub`, `User.identity_provider`).
- Use `user:<sub>` as the OpenFGA user id. Do **not** use email (mutable) or the
  local integer PK (not portable across services) as the FGA subject.
- On an Entra pivot, `sub` semantics differ per IdP; plan a migration/mapping
  step for existing tuples if the subject id format changes. Keeping `sub`
  isolated behind `user:<sub>` in one place (gx-auth) keeps that blast radius
  small.

## The subject contract

The rule, in full: **a valid subject is `user:<sub>`, where `sub` is the claim
the IdP issued. There is no other kind of subject, and no fallback.** A
principal with no `sub` — a Django superuser, an admin created before any OIDC
wiring — has no OpenFGA subject at all. `User.fga_subject` returns `None` for
it, and callers must deny. ([ADR 0003](./decisions/0003-idp-sub-is-the-only-subject.md).)

Why so strict: **the store is shared.** A locally-invented id is unique inside
one database and meaningless outside it, so gx-auth's pk 3 and a consumer's pk 3
would both be `user:3` — two unrelated people holding each other's grants. This
is a sharper objection than "not portable" above, and it is why the old
`f"user:{self.sub or self.pk}"` fallback was removed.

### What a consumer should do

Check for the missing subject and deny **explicitly**, so a data problem is
distinguishable from a real denial:

```python
if user.is_superuser:
    return True                  # break-glass: service-local policy, not OpenFGA
if not user.sub:
    logger.error("user %s has no sub, so no OpenFGA subject; denying", user.pk)
    return False
return authz.check(f"user:{user.sub}", "can_view", f"project:{pid}")
```

`gx-auth-sdk` will not do this for you silently: it **raises `ValueError`** on an
obviously malformed id (`"user:"`, `"alice"`, embedded whitespace) rather than
passing it to the engine. OpenFGA answers a malformed `Check` with
`allowed: false`, which is indistinguishable from a legitimate denial — so
without that check, a bad row surfaces as a permissions mystery for one user.

### Break-glass is out of scope on purpose

Superuser access is a **service-local** decision (the short-circuit above). It is
deliberately invisible to OpenFGA and to gx-auth's `GrantAudit`: break-glass
belongs to the service operating it, and representing it in the shared store
would make it broader, not better audited.

### Known gap: you cannot grant before first login

`CognitoOIDCBackend` creates the local `User` row on first login, so until then
there is no `sub` to key a tuple against. The `sub` exists at the IdP — Cognito
assigns it at pool-user creation — but gx-auth has no way to fetch it. Closing
this needs an IdP lookup on the write path (`AdminGetUser` / MS Graph), which is
new surface: today the service only ever *receives* identity, it never queries
for it. Tracked in [issue #4](https://github.com/dfornika/gx-auth/issues/4).

## What gx-auth exposes

- `POST /api/authz/check` — decision endpoint (thin wrapper over OpenFGA `Check`),
  for callers that prefer a domain API over the raw engine, and for audit.
- `GET  /api/authz/list-objects` — `ListObjects` wrapper.
- `POST /api/authz/grants` / `DELETE /api/authz/grants/...` — domain grant/revoke,
  audited (the write path from doc 003).
- `GET  /api/auth/me`, API-key management — mirrors GX Core's `accounts` app.

Hot-path `Check`s from services may also talk to OpenFGA directly (doc 001); the
`gx-auth` decision endpoint exists for convenience, audit, and engine
abstraction, not as a mandatory hop.
