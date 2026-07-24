# OpenFGA authorization model

`model.fga` is the canonical authorization model for the platform, in OpenFGA
DSL. It is explained in [`../../docs/002-authorization-model.md`](../../docs/002-authorization-model.md).

## Authoring & writing the model

Model authoring/writing uses the **OpenFGA CLI** (`fga`), which understands the
`.fga` DSL. The runtime Python SDK (`authz/services/fga.py`) is only used for
`check` / `list_objects` / tuple writes.

The `fga` CLI is available as the `openfga/cli` container image. The justfile
wraps the common flows:

```shell
# One-time: create a store and capture its id into your .env as FGA_STORE_ID
just fga-store-create

# Write / update the model from model.fga (prints the new authorization model id)
just fga-model-write

# Sanity-check the DSL parses
just fga-model-validate
```

After `fga-store-create`, put the returned store id in `.env` as `FGA_STORE_ID`.
Leave `FGA_MODEL_ID` empty to always use the store's latest model, or pin it for
reproducibility.

## Seeding tuples

`seed.tuples.csv` is a demo relationship set that mirrors the `model.tests.yaml`
fixture. Load it into the running store (idempotent) with:

```shell
just fga-seed
```

Then the live store answers the same way the offline tests assert, e.g.
`just fga-check user:alice can_delete project:demo` → `allowed: true`.

Batch-import any CSV/JSON/YAML file with `just fga-tuple-import <path>`. The CSV
header is:

```
user_type,user_id,user_relation,relation,object_type,object_id,condition_name,condition_context
```

For the current RBAC model only the first six columns are used. The optional
`user_relation` (usersets, e.g. `group:lab-x#member`) and
`condition_name`/`condition_context` (ABAC conditions) support the "growing from
here" additions in docs/002.

## Testing the model

`model.tests.yaml` asserts expected decisions against a fixture graph — run it
offline (no server needed) with:

```shell
just fga-model-test
```

It covers the RBAC matrix (admin/member/viewer → can_view/create/edit/delete/
administer) and leaf resources inheriting from their project. Extend it whenever
you touch `model.fga` — it is the safety net for model changes (see docs/003
"Failure modes"). `just fga-model-validate` just checks the DSL parses.
