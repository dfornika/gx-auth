# 002 — Authorization model

Role-based access control over a nested project hierarchy, written in
OpenFGA's modelling language. The source of truth is
[`src/fga/model.fga`](../src/fga/model.fga). Its behaviour is pinned down by
[`src/fga/model.tests.yaml`](../src/fga/model.tests.yaml), which runs offline
(`just fga-model-test`).

## The rule to remember

**Users are assigned roles, never permissions.** Permissions are derived from
roles, and a role on a project flows down to every project beneath it. So
there are only two things to manage:

- which users hold which role on which project, and
- which project is each project's parent.

## Projects: roles, permissions, inheritance

```
type project
  relations
    define parent: [project]          # no tuple for a top-level project
    define platform: [platform]       # see "Who may manage roles" below

    # roles: the only relations you assign
    define admin:  [user] or admin from parent or admin from platform
    define member: [user] or member from parent
    define viewer: [user] or viewer from parent

    # permissions: derived, and what services Check
    define can_view:       admin or member or viewer
    define can_create:     admin or member
    define can_edit:       admin or member
    define can_delete:     admin
    define can_administer: admin
```

| permission     | admin | member | viewer |
|----------------|:-----:|:------:|:------:|
| can_view       |   ✓   |   ✓    |   ✓    |
| can_create     |   ✓   |   ✓    |        |
| can_edit       |   ✓   |   ✓    |        |
| can_delete     |   ✓   |        |        |
| can_administer |   ✓   |        |        |

`admin from parent` means "anyone who is an admin of this project's parent".
The parent follows the same rule, so a role granted high in the tree reaches
everything below it.

Rules the **application** must enforce, because OpenFGA does not:

- **No cycles.** Never make a project the parent of one of its ancestors.
- **Bounded depth.** Keep nesting shallow (about 5 levels). This stays well
  inside OpenFGA's default resolution limit of 25.

### The cost of inheritance

Effective access is no longer visible from one project:

- Removing a role on a child does not remove access the user still inherits
  from an ancestor.
- Changing a project's parent instantly changes access to everything under it.

The admin inspector (`/admin/fga/expand/`) shows why a relation resolves the
way it does.

## Resources inherit from their project

```
type sample
  relations
    define project: [project]
    define can_view:   can_view from project
    define can_edit:   can_edit from project
    define can_delete: can_delete from project
```

`analysis_output` is identical. Neither type adds anything to manage: access
comes from the project, including roles inherited from its ancestors.

## Who may manage roles: `platform`

The grants API is itself authorized ([ADR 0004](./decisions/0004-control-plane-authorizes-itself.md)):
changing a role on a project needs `can_administer` there. The `platform` type
covers the two cases that rule leaves open.

```
type platform
  relations
    define admin:    [user]   # may manage roles on any project
    define delegate: [user]   # a service trusted to act for an end user
```

- **Bootstrap.** A new project has no admin. A platform admin can appoint one.
- **Services acting for people.** A delegate service names the end user it
  acts for, and the grant is checked against that user (doc 004).

The `project#platform` edge is **never stored**. gx-auth adds it as a
contextual tuple only while authorizing a grant. A platform admin can fix any
project's roles, but has no access to project data until they grant
themselves a role, which is audited. Platform roles are written only with
`manage.py grant_platform_role`.

## What services ask

| question                    | call                                      |
|-----------------------------|-------------------------------------------|
| may U edit project X?       | `Check(user:U, can_edit, project:X)`      |
| may U view sample S?        | `Check(user:U, can_view, sample:S)`       |
| may U manage X's members?   | `Check(user:U, can_administer, project:X)`|
| which projects can U see?   | `ListObjects(user:U, can_view, project)`  |
| which samples can U see?    | `ListObjects(user:U, can_view, sample)`   |

`ListObjects` on a user with a role near the top of the tree returns the whole
subtree. That is cheap for projects, and the thing to measure for samples (doc
003).

## Changing the model

- **Derived relations** (`can_*`) have no stored tuples, so changing them is
  free.
- **Stored relations** (`admin`, `member`, `viewer`, `parent`, `project`) are
  a data migration. OpenFGA never migrates tuples. A removed relation makes
  checks fail with an error. A removed *type* silently drops every grant that
  depended on it, while its tuples remain.

## Possible additions

Add these only when a real requirement appears:

- **Groups.** Grant a role to a whole team in one tuple:
  `define member: [user, group#member] or member from parent`.
- **Conditions.** Gate a relation on request-time facts, such as an access
  level, an embargo date or a consent code.
