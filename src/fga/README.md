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
`just fga-check user:anne can_view project:root` → `allowed: true`.

Batch-import any CSV/JSON/YAML file with `just fga-tuple-import <path>`. The CSV
header is:

```
user_type,user_id,user_relation,relation,object_type,object_id,condition_name,condition_context
```

`user_relation` expresses usersets (e.g. a `group:lab-x#member` grant);
`condition_name` + `condition_context` carry a condition (e.g. the SMS access
level: `meets_access_level`, `{"user_level":5}`).

## Testing the model

`model.tests.yaml` asserts expected decisions against a fixture graph — run it
offline (no server needed) with:

```shell
just fga-model-test
```

It covers hierarchy inheritance (downward only), role nesting, group grants,
leaf→project inheritance, and the SMS access-level condition (level sufficient /
too low / role-without-level / level-without-role). Extend it whenever you touch
`model.fga` — it is the safety net for model changes (see docs/003 "Failure
modes"). `just fga-model-validate` just checks the DSL parses.
