# ADR 0004 — The control plane authorizes its own API

- Status: Proposed
- Date: 2026-09-22

## Context

gx-auth's HTTP API authenticated callers by API key and then trusted them
completely. Any key holder could:

- write **any** relation on **any** object through `POST /api/authz/grants`,
  including `admin` on any project, and structural edges like `parent` that
  re-parent a whole subtree;
- ask `check` / `list-objects` about **any** user, which reveals who can see
  what.

The service guarding the rest of the platform was itself unguarded. Two further
facts shape the fix:

1. **Callers are mostly services.** A consumer like SDS calls the control plane
   with its *own* service-account key (`gx_auth_sdk.grant`). So the caller is
   "SDS", not the person who clicked "add member". An authorization rule
   evaluated against the caller would be evaluated against the wrong principal.
2. **Someone has to grant the first admin.** A new project has no admins, so a
   rule of "only admins manage roles" leaves nobody able to start.

## Decision

1. **Grants are authorized by the engine.** Granting or revoking a role on
   `project:X` requires the **actor** to hold `can_administer` on `project:X`,
   answered by OpenFGA like any other decision. Inherited admin (from a parent
   project) counts. Every policy check (`can_administer`, `delegate`) requests
   **higher consistency**, so a role revoked a moment ago cannot still
   authorize a control-plane action. The latency cost is confined to the
   control plane; the hot path keeps the engine's default.
2. **Only role relations are grantable over HTTP.** `policy.GRANTABLE_RELATIONS`
   (today `project`: `admin`, `member`, `viewer`) is an explicit allowlist.
   Structural edges (`parent`, `project`, `platform`) belong to resource sync
   (docs/003). Platform roles are written only by the `grant_platform_role`
   management command. Anything else is a 422 before the engine is called.
3. **A `platform` type holds control-plane roles.** One object,
   `platform:<GXAUTH_PLATFORM_ID>` (default `platform:gx`), with:
   - `admin`: may manage grants on any project, including a brand-new one.
     This is the bootstrap answer.
   - `delegate`: a service trusted to name the end user it acts for (below).
     It grants no project access by itself.
4. **Platform admin is a control-plane role, not a data role.** The model has
   `admin from platform` on `project`, but the `project#platform` edge is **not
   stored**: the control plane supplies it as a contextual tuple only when
   authorizing a grant. On the hot path, a platform admin therefore sees no
   project data. To read a project they must grant themselves a role, and that
   grant is audited.
5. **The actor is the caller, unless a delegate says otherwise.** A caller that
   holds `delegate` on the platform may pass `on_behalf_of: user:<sub>`. The
   grant is then authorized against *that* user, and `GrantAudit` records both
   the calling service (`performed_by`) and the end user (`on_behalf_of`). A
   non-delegate that sends `on_behalf_of` gets a 403. It is never silently
   evaluated as itself.
6. **Callers query only themselves.** `check` / `list-objects` answer about
   the caller's own subject. Asking about another subject requires `delegate`.
7. **No change reaches the store without a committed audit row.** OpenFGA
   cannot join a database transaction, so the two writes are never atomic.
   Instead, `authz/services/grants.py` commits the `GrantAudit` row as
   `pending` *before* the engine write, then marks it `applied` or `failed`.
   If the process dies in between, or the status update fails, the row stays
   `pending`. The outcome is then unknown, but recorded.
   `manage.py reconcile_grant_audit` settles stale `pending` rows by reading
   the store. It leaves rows superseded by a later change to the same tuple
   for a human. This covers grants made through gx-auth only. Comparing the
   whole audit log against the live store (drift from writes that bypassed
   gx-auth) is still the broader reconciliation job in docs/003.

## Consequences

- **Delegation is trust, made explicit.** A delegate can assert any end user,
  including a platform admin. That is the trade this option makes: a small,
  listed, audited set of services is trusted to report the end user honestly.
  The trust lives as a tuple in the store rather than in configuration, and
  every use is recorded. Grant `delegate` sparingly.
- **Hardening path: forward the user's token.** A later step can have
  delegates pass the end user's IdP token, validated by gx-auth, instead of
  asserting `on_behalf_of`. That removes the trust without changing rule 1.
  It needs shared JWT validation (see the review note on token validation)
  and a story for background jobs that have no user token.
- **Bootstrapping a deployment** is now: create the store and write the model
  (`fga_bootstrap`), then `grant_platform_role admin <sub>` for the operators
  and `grant_platform_role delegate <client-sub>` for each consuming service.
- **Hot-path consumers are unaffected.** Services calling OpenFGA directly
  (docs/001) see no change, and platform admins gain no data access there.
- **Not addressed here:** OpenFGA itself is still unauthenticated. Anything with
  network reach to the engine can write tuples directly, bypassing all of the
  above. That is a separate item, and it limits how much this ADR buys until
  it is fixed.
- **Not addressed:** removing a project's last admin is allowed. Platform
  admins can recover from it.

## Alternatives rejected

- **The service is the actor.** Each service would need admin on every project
  it manages, which amounts to a platform admin with extra steps. The audit log
  could never say which person made a change.
- **Django superuser bypass for bootstrap.** Simpler, but it moves an
  authorization decision back into Python, where OpenFGA and the audit log
  cannot see it. That runs against ADR 0001 and CLAUDE.md.
- **Storing `project#platform` edges.** This would work for bootstrap, but it
  would give platform admins read and delete access to every project's data on
  the hot path, a far broader role than "can fix grants". It would also need
  a structural write for every new root project.
