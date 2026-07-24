# 002 — Authorization model

The current model is **role-based access control (RBAC)** with a **nested project
hierarchy**, expressed in OpenFGA. The canonical version is
[`src/fga/model.fga`](../src/fga/model.fga); this document explains it.

## The one rule to hold in your head

**You assign users to *roles*; you never assign *permissions*.** Permissions are
computed from roles. A role granted on a project also flows **down** to that
project's descendants. So the management surface is just two operations: assign a
role to a user on a project, and (when creating a sub-project) set its parent.

## Roles, permissions, and inheritance

```
type project
  relations
    define parent: [project]                       # top-level projects have no parent

    # role assignments — each role inherits itself from the parent (downward)
    define admin:  [user] or admin from parent
    define member: [user] or member from parent
    define viewer: [user] or viewer from parent

    # permissions — derived from roles; what apps Check
    define can_view: admin or member or viewer
    define can_create: admin or member
    define can_edit: admin or member
    define can_delete: admin
    define can_administer: admin
```

| permission | admin | member | viewer |
|---|:--:|:--:|:--:|
| can_view | ✓ | ✓ | ✓ |
| can_create | ✓ | ✓ | |
| can_edit | ✓ | ✓ | |
| can_delete | ✓ | | |
| can_administer | ✓ | | |

`admin from parent` means "anyone who is admin of this project's parent." Because
the parent is itself a project with the same rule, roles recurse up the tree, so
a grant on an ancestor reaches every descendant.

## Managing it

```bash
just fga-tuple-write user:anne member project:1        # assign a role
just fga-tuple-write project:1 parent project:2        # project:2's parent is project:1
just fga-check       user:anne can_edit project:2      # -> true (inherited from project:1)
```

Two write-time rules the **application** enforces (not OpenFGA):

- **Max nesting depth** — GX Core caps this (≈5, hard cap ~8–10). This is a
  business rule; it stays far under OpenFGA's `resolve-node-limit` (default 25),
  so no engine tuning is needed.
- **No cycles** — never set a project's parent to one of its own descendants.

## The conceptual cost (go in eyes-open)

With hierarchy, **permissions are no longer local to a single project.** "Who can
edit project X" may be answered by a role granted several levels up. Consequences:

- Removing a user's role on a child does **not** revoke access if they still hold
  a role on an ancestor — "why can they still see this?" becomes a walk up the tree.
- Re-parenting a project (change its `parent` tuple) instantly changes access for
  everything beneath it.

That is the deliberate trade: grant once high in the tree and it covers everything
below, in exchange for effective permissions not being obvious from one node.

## Resources inherit from their project

`sample` and `analysis_output` belong to a project and inherit its permissions —
and since the project inherits from its ancestors, resources transitively pick up
ancestor roles too. No extra management; you still only assign roles on projects.

```
type sample
  relations
    define project: [project]
    define can_view: can_view from project
    define can_edit: can_edit from project
    define can_delete: can_delete from project
```

## What apps Check

| Question | Call |
|---|---|
| may U edit this project? | `Check(U, can_edit, project:X)` |
| may U view this sample? | `Check(U, can_view, sample:X)` |
| may U manage members? | `Check(U, can_administer, project:X)` |
| which projects can U see? | `ListObjects(U, can_view, project)` — spans the subtree |
| which samples can U see? | `ListObjects(U, can_view, sample)` |

`ListObjects` for a user with a role high in the tree returns the whole subtree
beneath it — cheap for modest trees, and the main thing to watch at large fan-out
(see docs/003).

## Growing from here (when you're ready)

Additive, independently-versioned changes that don't alter how roles→permissions
or inheritance work:

- **Teams/groups** — a `group` type so a whole team can be granted a role in one
  tuple (`define member: [user, group#member] or member from parent`).
- **Attribute conditions (ABAC)** — OpenFGA conditions to gate a relation on
  request-time context (e.g. a numeric access level, embargo dates, consent codes).

Reach for these only when a real requirement demands them.
