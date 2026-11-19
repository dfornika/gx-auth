# gx-auth design docs

gx-auth is a shared **authorization** service for a genomics platform. It is a
Django control plane over [OpenFGA](https://openfga.dev), a relationship-based
decision engine. Authentication stays with the cloud identity provider: AWS
Cognito today, possibly Azure Entra ID later.

## Read in order

1. [001 — Architecture](./001-architecture-overview.md). The two layers, how
   services use them, and the constraints behind the design.
2. [002 — Authorization model](./002-authorization-model.md). Roles on
   nested projects, derived permissions, resources inheriting from projects,
   and the `platform` type.
3. [003 — Integration and tuple sync](./003-integration-and-sync.md). How
   services check, who writes which tuples, and the consistency and
   reconciliation problems. The hardest part of the design.
4. [004 — Identity and tokens](./004-identity-and-tokens.md). Thin tokens,
   the `user:<sub>` subject contract, credentials, and the gx-auth API.

[STATUS.md](./STATUS.md) lists what is built and what is open.

## Decisions

- [0001 — Use OpenFGA as the decision engine](./decisions/0001-use-openfga-rebac.md)
- [0002 — Keep authorization out of the identity provider](./decisions/0002-cloud-neutral-identity.md)
- [0003 — Only the IdP `sub` is a subject](./decisions/0003-idp-sub-is-the-only-subject.md)
- [0004 — The control plane authorizes its own API](./decisions/0004-control-plane-authorizes-itself.md)

ADRs record a decision as it was made. Later changes go in a new ADR, or a
dated note at the end of the old one, rather than a rewrite.
