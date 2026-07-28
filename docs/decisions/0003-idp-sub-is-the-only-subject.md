# ADR 0003 — Only the IdP `sub` is a valid authorization subject

- Status: Proposed
- Date: 2026-07-28

## Context

`gx-auth` keys OpenFGA subjects as `user:<sub>`, on the premise that `sub` comes
from the IdP (ADR 0002, doc 004). Wiring up the first real consumer —
`sequence-data-submission-service` — surfaced the case that premise does not
cover: **a service holds accounts that never came from the IdP.** Django
superusers, admins created before any OIDC wiring, service accounts. Their `sub`
is empty, so `user:<sub>` renders as the meaningless `user:`.

The contract was never stated, so two places in `gx-auth` had already answered it
by *inventing* an id:

- `User.fga_subject` fell back to the local pk — `f"user:{self.sub or self.pk}"`.
- `create_api_key` minted `svc-<username>` for service accounts.

Both are unsafe, and for a reason sharper than doc 004's "not portable": **the
store is shared across services.** A locally-invented id is unique inside one
database and meaningless outside it, so this service's pk 3 and a consumer's
pk 3 are *both* `user:3` — two unrelated people holding each other's grants.
`svc-catalog` has the same problem: two services can each mint it.

The failure is also silent. OpenFGA answers a malformed `Check` with
`allowed: false`, which is indistinguishable from a legitimate denial — so a
data problem surfaces as a permissions problem, at the point of use, for one
user.

## Decision

1. **Only the IdP `sub` is a valid subject.** `user:<sub>` and nothing else. No
   local primary keys, no synthetic subs, no reserved prefixes.
2. **A principal with no `sub` is not representable.** `User.fga_subject`
   returns `None`; callers must deny. There is no fallback.
3. **Service accounts are IdP principals like any other** — Cognito app clients
   (`client_credentials`) or Entra app registrations. They carry a real `sub`
   and are ordinary `user:<sub>` subjects. No `service_account` type is added to
   the model.
4. **API keys do not introduce a subject.** A key identifies a user who already
   has one; `create_api_key` requires `--sub` rather than inventing one.
5. **Break-glass access is service-local policy, deliberately outside OpenFGA.**
   A superuser short-circuit (`if user.is_superuser: return True`) is the
   sanctioned pattern.
6. **A malformed id raises rather than denies.** `gx-auth-sdk` rejects an
   obviously broken id before the engine call, so the data bug is reported as a
   data bug.

## Consequences

- **One subject space, one rule.** `model.fga` is untouched — no second subject
  type for every relation to accept, and no convention for consumers to each
  reinvent and collide over.
- **Superuser action is invisible** to the shared store and to `GrantAudit`.
  Accepted deliberately: break-glass belongs to the service operating it, and
  representing it in the shared store would make it *broader*, not more audited.
- **Every principal needing authorization must exist in the IdP.** This is the
  real operational cost, and it lands hardest on service accounts, which now
  require an IdP registration where a local row used to do.
- **Grants cannot precede a user's first login — yet.** `CognitoOIDCBackend`
  creates the local row on first login, so there is no `sub` to key a tuple
  against before then. The `sub` *does* exist (Cognito assigns it at pool-user
  creation), but `gx-auth` has no way to fetch it: closing this needs an IdP
  lookup on the write path (`AdminGetUser` / MS Graph), which is new surface —
  today the service only ever receives identity, never queries for it. Tracked
  in issue #4.
- **A missing `sub` fails closed and loudly** rather than closed and silently. A
  caller that wants a plain denial checks for it explicitly.
- **An Entra pivot stays tractable.** Every tuple is keyed by `sub` and there is
  exactly one kind of subject to remap — which is what ADR 0002's "isolate the
  `sub` mapping" was reaching for.

## Alternatives rejected

- **A dedicated `service_account:<id>` type.** Type-level distinction the engine
  enforces, but it means a `model.fga` change, every role relation accepting
  `[user, service_account]`, and every consumer knowing which type to build. It
  buys nothing once service accounts are IdP-provisioned.
- **A reserved prefix inside `user:`** (`user:svc-…`, `user:local-…`). No model
  change, and doc 004 already gestured at it — but nothing enforces uniqueness
  across services, which is exactly the collision this ADR exists to close. This
  is what `create_api_key` had adopted by accident.
- **A synthetic `sub` minted at account creation.** Keeps `user:<sub>`
  universally true, but re-introduces a second identity authority: the whole
  point is that one issuer mints subjects. It also leaves "which authority does
  this sub come from?" unanswerable from the id alone.
