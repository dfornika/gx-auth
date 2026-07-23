# gx-auth

A dedicated, independently-deployable **authorization** service for the GX
platform — a Django Ninja control plane over an [OpenFGA](https://openfga.dev)
(relationship-based) decision engine.

It provides one shared, expressive authorization plane for services that
currently each roll their own (GX Core, the Sample Metadata Service, and future
services), while **authentication** stays with the cloud identity provider
(AWS Cognito today; Azure Entra ID as a supported future pivot).

- **Design docs:** [`docs/`](./docs) — start with
  [docs/README.md](./docs/README.md).
- **Code:** [`src/`](./src) — a lean sibling of `gx-core` (uv / `just` /
  django-ninja / mozilla-django-oidc) plus OpenFGA.

## The idea in one paragraph

Authentication and authorization are split. The IdP issues a **thin, identity-only**
token; every fine-grained decision is answered at request time by OpenFGA. The
genomics domain (recursive project hierarchy, deep sample/analysis containment,
per-project roles and access levels) maps naturally onto relationship-based
access control, giving far more expressiveness than a flat scope model — while
keeping the whole stack self-hostable and cloud-neutral.

## Status

Early scaffold. The authorization model and integration patterns are a starting
point for iteration. Two things to validate with a prototype before committing
(see [docs/003](./docs/003-integration-and-sync.md)): **tuple-sync consistency**
and **`ListObjects` performance** at realistic data volumes.
