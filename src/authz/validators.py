"""Structural validation for the fully-qualified ids the engine is handed.

Server-side counterpart to the SDK's ``gx_auth_sdk.ids``. These run as
pydantic field validators on the Ninja schemas, so a malformed id is rejected
at the API boundary — before a garbage tuple can be written to the store or a
silent false-deny returned from a Check.

See gx-auth issue #5.
"""

from __future__ import annotations

_NO_SUB_HINT = " An account with no IdP `sub` has no OpenFGA subject — deny before calling."


def validate_fga_id(value: str, field: str, *, empty_id_hint: str = "") -> tuple[str, str]:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string, got {value!r}")
    if any(c.isspace() for c in value):
        raise ValueError(f"{field} must not contain whitespace, got {value!r}")

    type_, sep, id_ = value.partition(":")
    if not sep:
        raise ValueError(
            f"{field} must be fully qualified as 'type:id', got {value!r} "
            "(e.g. 'user:abc123', 'project:42')"
        )
    if not type_:
        raise ValueError(f"{field} has an empty type, got {value!r}")
    if not id_:
        raise ValueError(f"{field} has an empty id, got {value!r}.{empty_id_hint}")
    return type_, id_


def validate_subject(value: str, field: str = "user") -> str:
    _, id_ = validate_fga_id(value, field, empty_id_hint=_NO_SUB_HINT)
    id_part, sep, relation = id_.partition("#")
    if sep and not relation:
        raise ValueError(
            f"{field} is a userset with an empty relation, got {value!r} "
            "(expected 'type:id#relation', e.g. 'group:lab-x#member')"
        )
    if sep and not id_part:
        raise ValueError(f"{field} has an empty id, got {value!r}")
    return value


def validate_object(value: str, field: str = "object") -> str:
    _, id_ = validate_fga_id(value, field)
    if "#" in id_ or "*" in id_:
        raise ValueError(
            f"{field} must be a concrete 'type:id', got {value!r} "
            "(usersets and wildcards are subjects, not objects)"
        )
    return value


def validate_type_name(value: str, field: str = "type") -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string, got {value!r}")
    if ":" in value or any(c.isspace() for c in value):
        raise ValueError(
            f"{field} must be a bare type name, got {value!r} (e.g. 'sample', not 'sample:1')"
        )
    return value


def validate_relation(value: str, field: str = "relation") -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string, got {value!r}")
    if any(c.isspace() for c in value):
        raise ValueError(f"{field} must not contain whitespace, got {value!r}")
    return value
