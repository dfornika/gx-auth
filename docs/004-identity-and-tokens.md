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
   app registrations both cover this natively. Represent a service account as its
   own subject in OpenFGA if it needs grants (`user:svc-gx-flow` or a dedicated
   `service` type).
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
