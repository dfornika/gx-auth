"""gx-auth-sdk — consumer SDK for the gx-auth authorization plane.

Core (no framework deps):
    check, list_objects, write_relationship, delete_relationship, Relationship
    grant, revoke, configure

With the `ninja` extra:
    require, StubHeaderAuth

The framework glue is imported lazily (PEP 562), on first *attribute access*
rather than at `import gx_auth_sdk` time. A core SDK that talks to OpenFGA over
HTTP has no reason to pull a web framework in on import — and doing so used to
break consumers, because importing `ninja` evaluates django-ninja's pydantic
settings model, which needs Django settings to already be configured. Any
`import gx_auth_sdk` before `django.setup()` (settings.py, a management command,
a REPL) therefore died with a wall of pydantic errors that named neither this
package nor the real problem. See issue #2.
"""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec

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

#: Lazily-loaded exports from the `ninja` extra -> the submodule defining each.
_EXTRA_EXPORTS = {
    "require": ".ninja",
    "StubHeaderAuth": ".identity",
}

# `find_spec` locates django-ninja without executing it, so `__all__` can report
# whether the extra is installed without triggering the import it guards.
_HAVE_NINJA = find_spec("ninja") is not None
if _HAVE_NINJA:
    __all__ += list(_EXTRA_EXPORTS)


def _settings_configured() -> bool:
    """Whether Django settings are loaded. False if Django is absent entirely."""
    try:
        from django.conf import settings
    except ImportError:  # pragma: no cover - django-ninja depends on django
        return False
    # A property on LazySettings; reading it does not trigger setup.
    return settings.configured


def __getattr__(name: str):
    """Resolve the `ninja`-extra exports on first use (PEP 562).

    Both failure modes get their own message, because the two are easy to
    confuse and the underlying exceptions say nothing useful about either.
    """
    module = _EXTRA_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    if not _HAVE_NINJA:
        raise ImportError(
            f"gx_auth_sdk.{name} requires django-ninja, which is not installed. "
            'Install the extra: pip install "gx-auth-sdk[ninja]" '
            "(or add gx-auth-sdk[ninja] to your dependencies)."
        )
    if not _settings_configured():
        raise ImportError(
            f"gx_auth_sdk.{name} imports django-ninja, which reads Django settings "
            "at import time — but settings are not configured yet. Access it after "
            "django.setup(): from AppConfig.ready(), inside a view, or at module "
            "scope in an app module rather than in settings.py."
        )

    value = getattr(import_module(module, __name__), name)
    globals()[name] = value  # cache: __getattr__ is not consulted again
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
