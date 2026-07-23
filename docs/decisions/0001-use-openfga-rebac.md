# ADR 0001 — Use OpenFGA (ReBAC) as the decision engine

- Status: Proposed
- Date: 2026-07-23

## Context

The platform needs a shared, expressive, cross-service authorization plane for
GX Core, SMS, and future services. Requirements:

- **Expressive**, domain-specific authorization — the genomics data model is a
  recursive project hierarchy with deep resource containment; access follows the
  data graph.
- **Cross-service** — one source of truth several services consult.
- **Cloud-neutral** — AWS today, but must survive a pivot to Azure. No lock-in.

Options considered:

- **Flat scope/role model (Ego-style `policy.READ`)** — simple, but coarse; does
  not express hierarchy or per-resource access without exploding the scope list.
- **Amazon Verified Permissions / Cedar** — expressive, but AWS-locked; violates
  the cloud-neutral constraint.
- **OpenFGA (Zanzibar-style ReBAC)** — relationship-based, self-hostable on
  Postgres, CNCF project, Python SDK, supports conditions (ABAC) and
  hierarchical inheritance.
- **SpiceDB / AuthZed** — the other mature Zanzibar implementation; strong
  consistency story and list performance.
- **Oso** — policy-as-code + data; more RBAC/ABAC-flavored.

## Decision

Use **OpenFGA** as the decision engine, wrapped by a Django Ninja control plane
(`gx-auth`). ReBAC matches the hierarchical/relationship shape of the domain;
OpenFGA is self-hostable and cloud-agnostic; conditions cover future ABAC needs.

## Consequences

- We gain hierarchy-as-inheritance, group/team grants, and per-resource access
  without a combinatorial scope explosion.
- We take on OpenFGA as tier-0 stateful infrastructure (its own Postgres, HA,
  backups) and the **tuple-sync problem** (doc 003) — the main cost.
- `ListObjects` performance must be validated at realistic scale (doc 003).
- The control-plane wrapper keeps the engine swappable: **SpiceDB** is the
  designated fallback to benchmark against if OpenFGA hits consistency or
  list-performance limits.
