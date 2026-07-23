# 001 — Architecture overview

## What gx-auth is (and is not)

`gx-auth` is a shared **authorization** service. It answers one question for the
rest of the platform:

> Can subject `S` perform action `A` on resource `R`?

It is **not** an authentication service and **not** an identity provider. Login,
MFA, the user directory, and token issuance stay with the cloud IdP (AWS Cognito
today; Azure Entra ID is a supported future pivot — see doc 004).

This separation is the single most important design decision in the system.
Authentication answers *"who are you"*; authorization answers *"what may you
do"*. Conflating them is what makes the incumbent designs hard to evolve. By
keeping them apart:

- the IdP stays swappable (Cognito ↔ Entra is a config change, not a rewrite);
- authorization logic can be as expressive as the domain needs, without being
  constrained by what fits in a JWT claim.

## The two-layer shape

A "authorization service" actually splits into two layers here:

```
┌─────────────────────────────────────────────────────────────────┐
│  gx-auth (this repo) — the CONTROL PLANE (Django Ninja)           │
│  • owns the authorization model (the .fga schema)                 │
│  • domain-level grant/revoke API ("add U as editor on project P") │
│  • tuple sync from services' resources -> OpenFGA                 │
│  • audit log of grants and (optionally) decisions                 │
│  • admin surface                                                  │
└───────────────┬───────────────────────────────────────────────────┘
                │ manages / writes
                ▼
┌─────────────────────────────────────────────────────────────────┐
│  OpenFGA — the DECISION ENGINE / DATA PLANE                       │
│  • stores relationship tuples (study:abc#editor@user:xyz)         │
│  • answers Check / ListObjects in low single-digit ms             │
│  • backed by its own Postgres                                     │
└─────────────────────────────────────────────────────────────────┘
```

We do **not** reimplement the decision engine. OpenFGA is the engine; `gx-auth`
is the domain-aware wrapper, sync layer, and admin/audit surface around it.

## Target topology

```
   AWS Cognito / Azure Entra ID
        │  OIDC (identity only: sub, email, coarse role)
        ▼
  ┌───────────┐   ┌───────────┐   ┌─────────────┐
  │ Service A │   │ Service B │   │  (future…)  │   each validates the OIDC
  └─────┬─────┘   └─────┬─────┘   └──────┬──────┘   token itself; enforcement
        │ Check(...)    │ Check(...)     │ Check    stays inside each service
        └───────────────┴────────────────┴──────────┐
                                                     ▼
                                              ┌────────────┐
                     grant/revoke, model  ───▶│   OpenFGA  │◀── tuple writes
                     (via gx-auth control      └────────────┘    (from gx-auth)
                      plane)
```

Two integration paths, deliberately different:

- **Hot path (reads):** services call OpenFGA's `Check` directly at their
  enforcement points. Low latency, no extra hop, and it keeps `gx-auth` off the
  critical request path so it is not a single point of failure for every request.
- **Management path (writes):** grants, revocations, and model changes go
  **through the `gx-auth` control plane**, which translates domain operations
  into tuple writes, records an audit trail, and gives us one place to swap the
  engine if ever needed.

## The cloud-neutral constraint

AWS/Cognito is the near-term target, but the design must survive a pivot to
Azure/Entra. Two consequences shape the whole system:

1. **The authorization engine must be self-hostable and cloud-agnostic.** This
   rules out AWS-locked engines (Amazon Verified Permissions / Cedar). OpenFGA
   runs anywhere on a standard Postgres. See
   [ADR 0001](./decisions/0001-use-openfga-rebac.md).
2. **Authorization must live entirely in gx-auth/OpenFGA, never in the IdP.** No
   permissions baked into Cognito groups or a Pre-Token-Generation Lambda. The
   token carries identity only. See
   [ADR 0002](./decisions/0002-cloud-neutral-identity.md) and doc 004.

## Why ReBAC fits the domain

The genomics data model is deeply hierarchical and relationship-shaped:

- GX Core: a recursive `Project` tree, with `Sample` as an umbrella over
  `BioSample` / `Library` / `SequencedLibrary`, plus `ConsensusSequence` /
  `Assembly` / `Alignment`, and `AnalysisRun` → `AnalysisOutput`.
- SMS: flat `Project` → `Sample`, with role- and access-level-based scoping.

Access naturally follows the data graph: "an editor of a project can edit every
sample under it" is one rule, not thousands of per-object grants. That is exactly
what relationship-based access control (ReBAC / Google Zanzibar) expresses well,
and why OpenFGA is a better fit than a flat scope/role model (like Ego's
`policy.READ` scopes). The full model is in doc 002.

## Rollout

Do not big-bang this. Services keep their built-in authorization for the short/medium
term. Stand up `gx-auth` + OpenFGA and create experimental proof-of-concept client services.
Prove the tuple-sync strategy and `ListObjects` performance there, then migrate
other services later once the pattern is battle-tested.
