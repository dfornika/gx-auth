# 004 — Identity and tokens

## The IdP authenticates; gx-auth does not

Users sign in with the IdP (Cognito today). Each service validates the
resulting token itself. The token's `sub` claim is the only identity
authorization uses: in OpenFGA a person is `user:<sub>`.

Cognito and Entra both publish standard OIDC discovery, so to every service an
IdP is just an issuer, some endpoints and a set of signing keys.

## Thin tokens

**No authorization in the token, and none in the IdP** (ADR 0002):

- no permissions in `cognito:groups`, or in Entra `roles`/`groups` claims;
- no Cognito pre-token-generation Lambda, or Entra claims-mapping policy,
  that injects permissions.

A token carries `sub`, `email`, and at most a coarse flag such as "platform
staff". Every real decision is made at request time by OpenFGA.

This keeps the IdP swappable. Moving from Cognito to Entra changes
configuration, not the authorization model. It also keeps authorization
expressive: hierarchy and sharing do not fit in a token claim.

One permitted use of IdP groups is a **login gate**, such as
`OIDC_REQUIRED_GROUP`: whether someone may sign in at all, never what they may
do afterwards.

## The subject contract

**A subject is `user:<sub>`, with `sub` exactly as the IdP issued it. There is
no other kind of subject and no fallback** (ADR 0003).

- Never use email (it can change) or a local database id. The store is
  shared, so one service's user 3 and another's user 3 would both be
  `user:3` and hold each other's grants.
- An account with no `sub` has no subject. `User.fga_subject` returns `None`,
  and the caller must deny. Typical cases are a local Django superuser and an
  account created before OIDC was set up.
- Service accounts are IdP principals too (Cognito app clients, Entra app
  registrations). Each has a real `sub` and is an ordinary `user:<sub>`.

A consumer should deny that case explicitly, so a data problem cannot pass
for a real denial:

```python
if user.is_superuser:
    return True                  # break-glass: this service's own policy
if not user.sub:
    logger.error("user %s has no sub; denying", user.pk)
    return False
return authz.check(f"user:{user.sub}", "can_view", f"project:{pid}")
```

`gx-auth-sdk` raises `ValueError` on a malformed id (`"user:"`, `"alice"`,
embedded whitespace) instead of passing it to OpenFGA, which would answer
`False`.

**Break-glass is service-local by design.** A superuser short-circuit lives in
the service that runs it. It is invisible to OpenFGA and to gx-auth's audit
log. Putting it in the shared store would make it broader, not better
audited.

## Credentials

| credential | used for | subject |
|---|---|---|
| Interactive user token (OIDC) | people using a service | `user:<sub>` |
| Machine token (Cognito `client_credentials`, Entra app) | service-to-service calls, automation | `user:<client sub>` |
| API key (issued by a service) | scripts and CLIs | the user who owns the key |

An API key identifies a user who already has a `sub`, and never introduces a
new subject. `create_api_key` requires `--sub`.

## Users who have not signed in yet

The local `User` row is normally created at first login. To grant a role
before then, create the row from the IdP's `sub` with
`manage.py provision_user <username> --sub <sub>`. Looking the `sub` up from
an email address automatically is
[issue #9](https://github.com/dfornika/gx-auth/issues/9).

## The gx-auth API

| endpoint | does | who may call |
|---|---|---|
| `POST /api/authz/check` | one `Check` | about yourself, or any subject if you are a delegate |
| `POST /api/authz/list-objects` | one `ListObjects` | same as `check` |
| `POST`/`DELETE /api/authz/grants` | grant or revoke a project role, audited | an actor with `can_administer` on the project |
| `GET /api/auth/me`, `/api/auth/api-keys` | identity, API-key management | any authenticated caller |

Callers authenticate with an API key (`Authorization: Bearer <key>`).

**Acting for someone else.** A service that holds `delegate` on the platform
may send `on_behalf_of: "user:<sub>"`. The grant is then checked against, and
audited as, that end user, with the service recorded alongside. This is how
"Alice added Bob" reaches the audit log rather than "SDS added Bob". The
trust is explicit, audited and narrow; ADR 0004 has the trade-offs.

Hot-path checks do not need gx-auth at all: services may call OpenFGA
directly (doc 001).

## Open questions

- **ID tokens or access tokens at APIs?** The SDK's `CognitoJWTAuth` accepts
  only ID tokens. APIs conventionally accept access tokens, and Cognito's
  machine-to-machine flow issues *only* access tokens. As written, service
  accounts cannot authenticate through it.
- **One shared token validator.** SDS validates bearer tokens by signature
  and expiry only, without checking issuer, audience or token type. Every
  service should use one validator from the SDK.
- **Moving to Entra.** Its `sub` differs from Cognito's, so existing tuples
  would need remapping. Because subjects only ever appear as `user:<sub>`,
  that is one mapping, done once.
