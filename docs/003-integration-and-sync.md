# 003 — Integration & tuple sync

This is the hardest part of the system. Read it before committing to the design.
ReBAC gives you an expressive, cross-service authorization plane; the price is
that **relationship tuples live in OpenFGA while the resources they describe live
in each service's own Postgres**, and those two stores must be kept consistent.

## Enforcement: services call `Check` (the read path)

Each service keeps its own request handling and calls `Check` at its enforcement
points. Nothing about a service's endpoints moves into gx-auth — it gets a shared
brain, not a shared gatekeeper.

```python
# GX Core, returning an analysis output
user_id = request.auth.sub          # from the validated OIDC token — identity only
allowed = fga.check(
    user=f"user:{user_id}",
    relation="can_view",
    object=f"analysis_output:{output_id}",
)
if not allowed:
    raise HttpError(403, "forbidden")
```

For list endpoints, use `ListObjects` to get the set of visible ids, then filter
the service's own query:

```python
ids = fga.list_objects(user=f"user:{user_id}", relation="can_view", type="sample")
qs = Sample.objects.filter(pk__in=[strip_type(o) for o in ids])
```

### The two performance realities

- **`Check`** is cheap (low single-digit ms), including the network hop. Fine on
  the hot path.
- **`ListObjects`** is materially heavier and is the #1 ReBAC scaling gotcha.
  Over large sample sets it can be slow or need pagination/streaming
  (`StreamedListObjects`). **Prototype this against your real per-project sample
  counts early.** If it does not hold up, the usual mitigations are: constrain
  lists to a single project scope first, denormalize enough into the service DB
  to pre-filter, or cache decisions briefly.

## The write path: keeping tuples in sync

When a resource is created/moved/shared, or a membership changes, the
corresponding tuple(s) must be written to OpenFGA. In a single database a `JOIN`
gives you this consistency for free; here it is a distributed-data problem. Pick
a strategy deliberately.

### Options

1. **Synchronous write-through via the gx-auth control plane (recommended start).**
   Domain operations ("create sample", "add editor", "publish project") call
   gx-auth, which writes the tuple(s) and records an audit entry. Simple, one
   code path, easy to reason about. Risk: a tuple write can fail after the
   resource commit (or vice versa) — mitigate with a reconciliation job (below).

2. **Transactional outbox in each service.** The service writes the resource and
   an outbox row in the same DB transaction; a relay drains the outbox to
   OpenFGA. Strong local atomicity, at-least-once delivery to FGA. More moving
   parts. This is the target for high write volumes.

3. **Event stream.** Services publish domain events; a gx-auth consumer projects
   them into tuples. Best decoupling, most infrastructure.

Start with **(1)** for GX Core adoption, and design the data model so a move to
**(2)** later is mechanical. In all cases the leaf-flattening decision from doc
002 keeps the number of tuples per resource small.

### Reconciliation is not optional

Whatever the write path, run a periodic **reconciliation/repair job** that walks
each service's resources and asserts the expected tuples exist in OpenFGA
(writing any missing, deleting any orphaned). Drift *will* happen — a failed
write, a manual DB edit, a bug. Reconciliation is what makes the eventual
consistency safe to rely on. gx-auth is the natural home for this job.

## Consistency semantics (read-after-write)

OpenFGA is eventually consistent by default. Most authorization is tolerant of a
brief lag, but some flows are not — e.g. a user is granted access and immediately
expects to see the resource. Handle those explicitly:

- Use OpenFGA's **higher-consistency** read option on the checks that need
  read-after-write.
- Or pass **contextual tuples** in the `Check` call to assert a just-made
  relationship that may not have propagated yet.

Decide per-flow; do not globally force strong consistency (it costs latency).

## Who owns which tuples?

- **Resource-derived tuples** (a sample belongs to a project, a leaf's `project`
  pointer): owned by the service that owns the resource, written via its chosen
  write path. gx-auth provides the endpoint/library; the service triggers it.
- **Grant tuples** (U is an editor of project P; team T is a viewer of P): owned
  by gx-auth's domain grant API, always audited.
- **The authorization model** (the `.fga` schema): owned by gx-auth exclusively,
  versioned, and rolled out via the OpenFGA CLI (see `src/fga/README.md`).

## Failure modes to design for

| Failure | Effect | Mitigation |
|---|---|---|
| OpenFGA unavailable | `Check` fails | Services fail **closed** (deny) on the hot path; short local cache optional. Treat OpenFGA as tier-0 infra (HA, backups). |
| Tuple write fails after resource commit | resource exists, no access | Reconciliation job; write-through returns error so caller can retry. |
| Model change breaks a relation | wrong decisions | Version the model; test with the FGA model test DSL before rollout; roll forward. |
| `ListObjects` too slow at scale | slow list endpoints | Scope-first, denormalize, or cache; prototype early. |

## Open questions to resolve before building the sync layer

1. **Sample/leaf volume:** how many leaf resources per project, and how big can
   the biggest project get? Drives `ListObjects` viability and the flatten
   decision.
2. **Group/team origin:** is there an org/team concept above `project` that
   grants access broadly, or is it all per-project grants today? Drives whether
   the `group` type earns its place on day one.
