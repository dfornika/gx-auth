# gx-auth design docs

`gx-auth` is a dedicated, independently-deployable **authorization** service for the
GX platform, built with Django Ninja and backed by [OpenFGA](https://openfga.dev)
(a Zanzibar-style relationship-based authorization engine).

It is the shared authorization *control plane* for services that currently each
roll their own authorization — starting with experimental proof-of-concept stub apps,
and possibly supporting existing apps like  **GX Core** and the **Sample Metadata Service (SMS)**,
 while authentication stays with the cloud identity
provider (AWS Cognito today, Azure Entra ID as a possible future pivot).

## Read in this order

1. [001 — Architecture overview](./001-architecture-overview.md)
   Why authN and authZ are split, the target topology, and the cloud-neutral
   constraint that shapes everything.
2. [002 — Authorization model](./002-authorization-model.md)
   Conventional RBAC in OpenFGA: roles (admin/member/viewer) on projects, a
   permission matrix derived from them, and resources inheriting from their
   project. Includes a "growing from here" section for later additions.
3. [003 — Integration & tuple sync](./003-integration-and-sync.md)
   How services call `Check` at their enforcement points, and how relationship
   tuples are kept in sync with resources that live in each service's own DB.
   This is the hardest part; read it before committing to the approach.
4. [004 — Identity & tokens](./004-identity-and-tokens.md)
   Cognito/Entra OIDC, the "thin token" discipline that keeps authorization out
   of the IdP, how service accounts and API keys fit, and the **subject
   contract**: `user:<sub>` or nothing.

## Decisions

Architecture Decision Records live in [`decisions/`](./decisions/).

- [0001 — Use OpenFGA (ReBAC) as the decision engine](./decisions/0001-use-openfga-rebac.md)
- [0002 — Cloud-neutral identity; keep authorization out of the IdP](./decisions/0002-cloud-neutral-identity.md)
- [0003 — Only the IdP `sub` is a valid authorization subject](./decisions/0003-idp-sub-is-the-only-subject.md)

## Status

Early scaffold. The authorization model and integration patterns here are a
**starting point for iteration**, not a finalized contract. The two things to
validate with a prototype before committing are called out in doc 003:
**tuple-sync consistency** and **`ListObjects` performance** at realistic data
volumes.
