# ADR 0002 — Cloud-neutral identity; keep authorization out of the IdP

- Status: Proposed
- Date: 2026-07-23

## Context

AWS Cognito is the near-term identity provider, but "decision makers" may favor
Azure, so the design must be able to pivot to Azure Entra ID without a rewrite.
A common shortcut is to carry authorization in the IdP — Cognito groups, or a
Pre-Token-Generation Lambda that injects permissions into the token. That
shortcut is both **IdP-locked** and **coarse**.

## Decision

1. **Split authentication from authorization.** The IdP authenticates; `gx-auth`
   + OpenFGA authorize. Services validate the OIDC token and then `Check`.
2. **Thin tokens.** The token carries identity only (`sub`, `email`, at most a
   coarse platform role). No permissions in `cognito:groups`, no
   permission-injecting Lambda / claims-mapping policy.
3. **Isolate the `sub` mapping.** Services use `user:<sub>` as the OpenFGA
   subject; the IdP-specific `sub` handling is confined so an issuer swap has a
   small blast radius.

## Consequences

- Cognito ↔ Entra becomes a configuration change (issuer, JWKS, endpoints), not
  an authorization re-model. Both are "just an OIDC issuer."
- Authorization is free to be as expressive as OpenFGA allows, unconstrained by
  what fits in a token claim.
- A slight cost: every fine-grained decision is a runtime `Check` rather than a
  claim read. This is the intended trade — real-time revocation and
  expressiveness over stale, coarse claims. (See doc 004.)
- If the IdP `sub` format changes on pivot, existing OpenFGA tuples keyed by the
  old subject need a migration; keeping the mapping in one place makes this
  tractable.
