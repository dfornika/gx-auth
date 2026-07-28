"""Validation for the fully-qualified ids the engine is handed.

OpenFGA accepts a malformed id and answers `allowed: false`. That makes a data
bug indistinguishable from a legitimate denial — surfacing as a permissions
problem, at the point of use, for one user. The canonical case is an account
with no IdP `sub`, whose subject renders as the meaningless `"user:"`.

These checks turn that into a `ValueError` at the caller instead. They are
deliberately shallow: they reject what is *obviously* not an id (a missing or
empty half, embedded whitespace) and otherwise stay out of the way, because
wrongly rejecting a valid id is worse than passing an odd one through. The
engine remains the authority on its own grammar.

See gx-auth issue #3.
"""

from __future__ import annotations

__all__ = ["validate_subject", "validate_object", "validate_type"]

#: The overwhelmingly common cause of an empty subject id, so name it directly.
_NO_SUB_HINT = (
    " An account with no IdP `sub` has no OpenFGA subject — deny it before calling, "
    "rather than asking the engine about 'type:'."
)


def _split(value: str, what: str, empty_id_hint: str = "") -> tuple[str, str]:
    """Split `type:id`, raising with the offending value quoted."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"gx-auth-sdk: {what} must be a non-empty string, got {value!r}")
    if value.strip() != value or any(c.isspace() for c in value):
        raise ValueError(f"gx-auth-sdk: {what} must not contain whitespace, got {value!r}")

    type_, sep, id_ = value.partition(":")
    if not sep:
        raise ValueError(
            f"gx-auth-sdk: {what} must be fully qualified as 'type:id', got {value!r} "
            "(e.g. 'user:abc123', 'project:42')"
        )
    if not type_:
        raise ValueError(f"gx-auth-sdk: {what} has an empty type, got {value!r}")
    if not id_:
        raise ValueError(f"gx-auth-sdk: {what} has an empty id, got {value!r}.{empty_id_hint}")
    return type_, id_


def validate_subject(value: str, what: str = "subject") -> str:
    """Check a subject: `type:id`, a userset `type:id#relation`, or `type:*`.

    Returns `value` unchanged so it can wrap an argument in place.
    """
    _, id_ = _split(value, what, _NO_SUB_HINT)

    # A userset ("group:lab-x#member") is a legitimate subject; an empty
    # relation after the '#' is not.
    id_part, sep, relation = id_.partition("#")
    if sep and not relation:
        raise ValueError(
            f"gx-auth-sdk: {what} is a userset with an empty relation, got {value!r} "
            "(expected 'type:id#relation', e.g. 'group:lab-x#member')"
        )
    if sep and not id_part:
        raise ValueError(f"gx-auth-sdk: {what} has an empty id, got {value!r}")
    return value


def validate_object(value: str, what: str = "object") -> str:
    """Check an object id: `type:id`. Usersets and wildcards are not objects."""
    _, id_ = _split(value, what)
    if "#" in id_ or "*" in id_:
        raise ValueError(
            f"gx-auth-sdk: {what} must be a concrete 'type:id', got {value!r} "
            "(usersets and wildcards are subjects, not objects)"
        )
    return value


def validate_type(value: str, what: str = "type") -> str:
    """Check a bare object type name, as taken by `list_objects`."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"gx-auth-sdk: {what} must be a non-empty string, got {value!r}")
    if ":" in value or any(c.isspace() for c in value):
        raise ValueError(
            f"gx-auth-sdk: {what} must be a bare type name, got {value!r} "
            "(e.g. 'sample', not 'sample:1')"
        )
    return value
