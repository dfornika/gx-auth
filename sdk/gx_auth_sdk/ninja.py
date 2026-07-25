"""django-ninja enforcement helper. Requires the `ninja` extra."""

from __future__ import annotations

import functools
import inspect

from ninja.errors import HttpError

from .client import check


def require(relation: str, obj: str):
    """Decorator enforcing `relation` on an FGA object before the view runs.

    `obj` is a format template filled from the view's path params, so the object
    id stays a per-service concern:

        @router.post("/projects/{pid}/samples")
        @require("can_edit", "project:{pid}")
        def create_sample(request, pid: int, payload): ...

    Raises 403 if the check fails. Apply it BELOW the router decorator.
    """

    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, **kwargs):
            target = obj.format(**kwargs)
            if not check(request.auth, relation, target):
                raise HttpError(403, f"forbidden: need {relation} on {target}")
            return view(request, **kwargs)

        # Preserve the view's signature so django-ninja still sees its path/body
        # params (wraps sets __wrapped__; set __signature__ too to be safe).
        wrapper.__signature__ = inspect.signature(view)
        return wrapper

    return decorator
