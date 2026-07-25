"""gx-auth-sdk — consumer SDK for the gx-auth authorization plane.

Core (no framework deps):
    check, list_objects, write_relationship, delete_relationship, Relationship
    grant, revoke, configure

With the `ninja` extra:
    require, StubHeaderAuth
"""

from .client import (
    Relationship,
    check,
    delete_relationship,
    list_objects,
    write_relationship,
)
from .config import configure
from .control_plane import grant, revoke

__all__ = [
    "check",
    "list_objects",
    "write_relationship",
    "delete_relationship",
    "Relationship",
    "grant",
    "revoke",
    "configure",
]

# Framework glue is optional — only available with the `ninja` extra installed.
try:
    from .identity import StubHeaderAuth
    from .ninja import require

    __all__ += ["require", "StubHeaderAuth"]
except ImportError:  # pragma: no cover - ninja extra not installed
    pass
