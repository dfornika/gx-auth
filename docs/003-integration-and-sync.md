# 003 — Integration and tuple sync

The hard part of this design is not the engine. It is that **tuples live in
OpenFGA, while the resources they describe live in each service's own
database**. Every relationship the model depends on has to be written to
OpenFGA, and kept correct as resources are created, moved and deleted. Read
this before integrating a service.

## Reads: services ask the engine

A service validates the caller's token, then checks at its enforcement points:

```python
subject = f"user:{request.user.sub}"          # identity from the token only
if not authz.check(subject, "can_view", f"project:{project_id}"):
    raise HttpError(403, "forbidden")
```

`authz` is `gx_auth_sdk`. It validates ids before calling the engine, and
raises on an obviously malformed one rather than letting OpenFGA answer
`False` (doc 004).

For lists, ask which ids are visible, then filter the service's own query.
The store is shared across services, so **keep only ids you own**:

```python
visible = authz.list_objects(subject, "can_view", "project")
ids = [o.removeprefix("project:") for o in visible]
Project.objects.filter(project_id__in=ids)
```

### Performance

- **Check** is cheap: single-digit milliseconds, including the network hop.
- **ListObjects** is the main scaling risk in any Zanzibar-style system. It
  is fine over projects. Over tens of thousands of samples it can be slow.
  This has **not yet been measured** at realistic volumes. If it does not
  hold up:
  - list within one project first;
  - check at project level and resolve resources locally;
  - or keep enough in the service database to pre-filter.

## Writes: keeping tuples in sync

Three kinds of tuple, with different owners:

| tuple | example | owner | written by |
|---|---|---|---|
| **Role grants** | `user:U admin project:P` | gx-auth | the grants API, audited |
| **Structure** | `project:P parent project:C`, `project:P project sample:S` | the service that owns the resource | the service, directly (today) |
| **Platform roles** | `user:U delegate platform:gx` | gx-auth operators | `grant_platform_role` |

The model itself (`model.fga`) belongs to gx-auth alone. It is versioned and
rolled out with the `fga` CLI (`src/fga/README.md`).

### Role grants (built)

`POST/DELETE /api/authz/grants` authorizes the actor, then goes through
`authz/services/grants.py`:

1. commit a `GrantAudit` row as `pending`;
2. write the tuple to OpenFGA;
3. mark the row `applied`, or `failed`.

The two stores cannot share a transaction, so this ordering is the guarantee:
no grant reaches OpenFGA without an audit row already committed. A crash
between steps leaves a `pending` row. `manage.py reconcile_grant_audit`
settles those rows by reading the store.

### Structural tuples (not built)

Nothing writes these yet. A service creating a project, sub-project or sample
must write the matching edge, and that write can fail after the service's own
commit succeeds. The options, from simplest to most robust:

1. **Write-through.** Write the tuple right after the resource commit, and
   repair failures later. Simple, but it relies on reconciliation (below).
2. **Transactional outbox.** The service commits the resource and an outbox
   row together, and a relay drains the outbox to OpenFGA. Delivery is
   at least once, but with more moving parts.
3. **Event stream.** Services publish domain events, and a consumer turns
   them into tuples. The most decoupled, and the most infrastructure.

The choice is open. Whichever it is, the fewer structural tuples a service
needs, the smaller this problem gets. A service that checks only at project
level, and maps its own resources to projects locally, needs just the
project's own edges.

### Reconciliation

Drift will happen: a failed write, a manual database edit, a bug. A periodic
job should compare each service's resources with the store, writing missing
tuples and removing orphans. Only the narrow audit-log case above exists today
(`reconcile_grant_audit`). The general job is unbuilt, and gx-auth is its
natural home.

## Consistency

OpenFGA reads are eventually consistent by default. Most checks tolerate a
brief lag. Where they cannot, choose per flow rather than globally:

- **Higher consistency.** Asks the engine to bypass its caches. gx-auth's
  wrapper (`fga.check(..., higher_consistency=True)`) uses it for every
  control-plane policy check, so a role revoked a moment ago cannot still
  authorize a change. The SDK does not expose it yet.
- **Contextual tuples.** Pass a just-written relationship along with the
  check. This suits "I was just granted access and want to see it now".

## Failure modes

| failure | effect | mitigation |
|---|---|---|
| OpenFGA unavailable | checks fail | Fail **closed** (deny). Treat OpenFGA as tier-0: HA and backups. |
| Tuple write fails after the resource commit | resource exists, no access | Reconciliation; write-through returns an error so the caller can retry. |
| Model change drops a relation | wrong decisions | Model tests before rollout; see "Changing the model" in doc 002. |
| `ListObjects` too slow | slow list pages | Scope to a project, check at project level, or pre-filter locally. |

## Open questions

1. **Who owns "project"?** If one project spans several services (metadata
   in SMS, reads in SDS), something must issue its id and own its lifecycle.
   If each service's projects are separate, their ids must not collide in the
   shared store.
2. **How many resources per project**, and how large is the largest project?
   This decides whether resource-level tuples are viable at all.
3. **Is there a team or organization above projects** that grants access
   broadly? If so, the `group` type earns its place now.
