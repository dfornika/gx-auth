# gx-auth

A shared **authorization** service for a genomics platform: a Django control
plane over the [OpenFGA](https://openfga.dev) decision engine.

Services each validate their users' identity tokens from the cloud identity
provider (AWS Cognito today), then ask OpenFGA whether the user may act.
gx-auth owns the authorization model, the audited API for granting and
revoking roles, and the admin tools around it.

- **Design:** [`docs/`](./docs/README.md). Start with the architecture doc.
- **Service:** [`src/`](./src/README.md). Django, django-ninja, uv, `just`.
- **SDK for consuming services:** [`sdk/`](./sdk/README.md).

## The idea

Tokens carry identity only. Every permission is answered at request time by
OpenFGA, from relationships such as "this user is an admin of this project"
and "this sample belongs to this project". Roles are granted on projects and
flow down nested projects to the resources in them. The whole stack is
self-hostable, so no part of the authorization ties the platform to one
cloud.

## Status

Experimental, with one consumer: sequence-data-submission-service, read path
only. See [docs/STATUS.md](./docs/STATUS.md) for what is built and what is
open.
