# 002 — Authorization model

This is the OpenFGA (ReBAC) model for the platform. The canonical, machine-usable
version lives at [`src/fga/model.fga`](../src/fga/model.fga); this document
explains the design behind it.

## Principles

- **One store, one model.** A single OpenFGA store with shared identity types
  (`user`, `group`) and a shared `project` type, plus service-specific resource
  types. This is what makes it a plane that *spans* services rather than two
  isolated silos.
- **Model roles and membership in FGA; keep pure-local computation in the app.**
  FGA owns the things worth sharing across services (roles, hierarchy, sharing).
  Purely local comparisons (e.g. SMS field-level masking) stay in the service.
- **Flatten containment where the data allows.** Prefer a denormalized `project`
  pointer on leaf resources over deep parent chains — fewer hops per `Check`, and
  a much smaller tuple-sync surface. See "Flatten vs. chain" below.

## The shared `project` type unifies SMS and GX Core

Some services have flat project structure; GX Core has a recursive hierarchy. One recursive-capable
`project` type covers both — services with flat project structure simply never write a `parent` tuple, so a flat
project is just a top-level project with no children. The three roles
(`admin` / `member` / `viewer`) line up across both services.

```
type project
  relations
    define parent: [project]

    # roles — direct grant OR inherited down the hierarchy
    define admin:  [user, group#member] or admin from parent
    define member: [user, group#member] or admin or member from parent
    define viewer: [user, group#member] or member or viewer from parent

    # SMS numeric access-level gate (separate grant carrying the user's level)
    define access_level_ok: [user with meets_access_level]

    # permissions the apps actually Check
    define can_administer: admin
    define can_edit:       member
    define can_view:       viewer
    define can_view_leveled: viewer and access_level_ok
```

Notes:

- `admin from parent` etc. give **downward inheritance**: an admin of a parent
  project is an admin of every descendant, recursively, with zero per-child
  tuples. That is GX Core's "access via membership in the project hierarchy."
- Roles nest: `member` includes `admin`, `viewer` includes `member`.
- `[group#member]` lets a whole team be granted a role in one tuple — see
  "Groups" below.

## Sample containment (GX Core leaf resources)

Every leaf resource inherits its permissions from its container. The minimal
pattern per type is three lines:

```
type sample
  relations
    define project: [project]
    define can_view:       can_view from project
    define can_edit:       can_edit from project
    define can_administer: can_administer from project
```

`biosample`, `library`, `sequenced_library`, `consensus_sequence`, `assembly`,
`alignment`, `analysis_run`, and `analysis_output` follow the same shape.

### Flatten vs. chain

GX Core's containment is deep:
`analysis_output → analysis_run → sequenced_library → library → biosample → sample → project`.
Two ways to model it:

| | Chain | Flatten (recommended) |
|---|---|---|
| Each leaf points at | its immediate container | directly at its `project` |
| `Check` on a deep leaf | ~6 hops of resolution | 1 hop |
| Tuple-sync surface | a tuple per parent link | one `project` tuple per leaf |
| Cost | slower checks, more tuples to keep in sync | must rewrite the pointer if a resource is re-parented (rare in genomics) |

Because a sample essentially never moves projects once created, we **flatten**:
write a direct `project` pointer on each leaf and inherit straight from the
project. This is as much a *sync-cost* decision as a latency one (doc 003).

## Numeric access levels → a condition

Some systems give each user an integer **access level** on a project (independent of
their role), and each sample a **minimum access level**. A user may view a sample
when their level ≥ the sample's minimum, *and* they hold a viewing role.

Modeled with an OpenFGA **condition** whose parameters come partly from the
stored tuple and partly from the check-time context:

```
condition meets_access_level(user_level: int, required_level: int) {
  user_level >= required_level
}
```

- **Grant time:** write `project:P#access_level_ok@user:U` with the condition and
  `{user_level: 5}` baked into the tuple. The role (`viewer`, etc.) is a
  *separate* tuple — mirroring "level is independent of role".
- **Check time:** Service (which knows the sample's minimum from its own DB) calls
  `Check(user:U, can_view_leveled, sample:S, context={required_level: 3})`.
  `can_view_leveled = viewer AND access_level_ok`, so both the role and the
  numeric gate must pass.

### Recommendation: keep other services numeric levels in-app for now

The comparison is purely local — services already store both the user's level and the
sample's minimum and does the check today. There is no cross-service value in
moving it into FGA yet. Let FGA own the other service's **roles and membership** (worth sharing)
and leave the integer compare where it works. The condition above documents that
it *can* be expressed in FGA if another service ever needs to honor access levels —
it is not a task to rush.

### Field-level minimum access: do NOT model in FGA

Per-field permission objects would explode the tuple count for no benefit.
Field masking is data-shaping that happens *after* authorization, once the
service knows the user's numeric level — a plain in-app filter over the field
list. FGA answers "can this user see this sample"; the service decides which
fields to return. Knowing where *not* to use FGA matters as much as the model.

## Groups / teams

`group` exists so access can be granted to a whole team in one tuple
(`project:P#member@group:lab-x#member`). Whether you need it on day one depends on
whether there is an org/team concept above `project` that grants access broadly,
or whether it is all per-project grants today (an open question — see doc 003).
The type is cheap to keep in the model even if unused initially.

## Conditions / ABAC headroom

GX Core has no attribute rules yet, but the condition mechanism above is the hook
for future ones: embargo/publication dates, consent/data-use codes, or
public-vs-controlled tiers all become conditions gating a relation on
request-time context. Add them when the requirements firm up; nothing in the
current model blocks them.

## What the apps Check

| Service | Question | Call |
|---|---|---|
| GX Core | view an analysis output | `Check(user:U, can_view, analysis_output:X)` |
| GX Core | edit a sample | `Check(user:U, can_edit, sample:X)` |
| GX Core | list visible samples | `ListObjects(user:U, can_view, sample)` |
| SMS | view a leveled sample | `Check(user:U, can_view_leveled, sample:X, context={required_level: N})` |
| any | administer a project | `Check(user:U, can_administer, project:X)` |

`ListObjects` is heavier than a point `Check` and is the main performance risk at
scale — prototype it against realistic sample volumes (doc 003).
