# 001 — Architecture overview

## What gx-auth is

gx-auth answers one question for the services of a genomics platform:

> May subject `S` perform action `A` on resource `R`?

It is an **authorization** service only. Login, MFA, the user directory and
token issuance belong to the cloud identity provider (IdP): AWS Cognito today,
possibly Azure Entra ID later (doc 004).

Keeping authentication and authorization apart is the central design choice:

- the IdP stays swappable, because nothing about permissions lives in it;
- authorization can be as expressive as the domain needs, rather than whatever
  fits in a token claim.

## Two layers

```
┌───────────────────────────────────────────────────────────┐
│ gx-auth — control plane (Django + django-ninja)           │
│  • owns the authorization model (src/fga/model.fga)       │
│  • grant/revoke API: "make U an admin of project P"       │
│  • authorizes its own callers (ADR 0004)                  │
│  • audit log of every grant and revoke                    │
│  • admin UI, including a read-only store inspector        │
└──────────────────────────┬────────────────────────────────┘
                           │ writes tuples, asks questions
                           ▼
┌───────────────────────────────────────────────────────────┐
│ OpenFGA — decision engine                                 │
│  • stores relationship tuples (project:p1#admin@user:abc) │
│  • answers Check / ListObjects                            │
│  • its own Postgres database                              │
└───────────────────────────────────────────────────────────┘
```

gx-auth does not make decisions itself. OpenFGA is the engine; gx-auth is the
domain-aware layer around it. The wrapper is kept thin
(`authz/services/fga.py`) so the engine could be swapped, with SpiceDB as the
fallback (ADR 0001).

## How services use it

```
  Cognito / Entra ── OIDC token (identity only) ──▶ each service
                                                        │
             ┌──────────────────────────────────────────┤
             │ reads: Check / ListObjects               │ writes: grant / revoke
             ▼                                          ▼
          OpenFGA  ◀──────── tuple writes ──────────  gx-auth
```

- **Reads (the hot path).** A service validates the user's token, then asks
  OpenFGA directly at each enforcement point. There is no extra hop, and
  gx-auth stays off the critical path.
- **Writes (the management path).** Role grants and revokes go through
  gx-auth, which authorizes the caller, writes the tuple and records an audit
  row.

Enforcement stays inside each service. gx-auth provides a shared answer, not a
shared gateway.

> **Open:** direct engine access is only safe once OpenFGA requires
> credentials. Today anything that can reach it can also *write* to it. See
> [STATUS.md](./STATUS.md).

## Constraints

1. **Cloud-neutral.** The engine must be self-hostable, which rules out
   AWS-only options such as Amazon Verified Permissions. OpenFGA runs anywhere
   on Postgres (ADR 0001).
2. **No authorization in the IdP.** No permissions in Cognito groups or in
   token-enrichment Lambdas. Tokens carry identity only (ADR 0002, doc 004).

## Why relationship-based access control

Access in this domain follows the data. Projects nest, and samples and
analysis outputs belong to projects. "An admin of a project can manage
everything under it" is one rule in a relationship-based model, rather than
thousands of per-object grants. That is what OpenFGA (a Zanzibar-style engine)
expresses well. Doc 002 has the model.

## Rollout

Not a big-bang migration. Existing services keep their own authorization. New
services prove the pattern first; sequence-data-submission-service is the
first consumer, through its pluggable `gxauth` backend. Services migrate only
once the two risks in doc 003 are understood: keeping tuples in sync, and
`ListObjects` performance.
