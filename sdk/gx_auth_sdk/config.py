"""Configuration resolution.

Reads from environment variables by default (the app is responsible for loading
its .env into the environment — e.g. via environs/django-environ). A consumer
may also call `configure(...)` explicitly to override.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    fga_api_url: str
    fga_store_id: str
    control_plane_url: str
    control_plane_api_key: str


_config: Config | None = None


def configure(
    *,
    fga_api_url: str | None = None,
    fga_store_id: str | None = None,
    control_plane_url: str | None = None,
    control_plane_api_key: str | None = None,
) -> Config:
    """Set the active config, falling back to environment variables per field."""
    global _config
    store_id = fga_store_id or os.environ.get("FGA_STORE_ID", "")
    if not store_id:
        raise RuntimeError(
            "gx-auth-sdk: FGA_STORE_ID is not set (env var or configure(fga_store_id=...))."
        )
    _config = Config(
        fga_api_url=fga_api_url or os.environ.get("FGA_API_URL", "http://localhost:8080"),
        fga_store_id=store_id,
        control_plane_url=control_plane_url or os.environ.get("GXAUTH_URL", "http://localhost:8000"),
        control_plane_api_key=control_plane_api_key or os.environ.get("GXAUTH_API_KEY", ""),
    )
    return _config


def get_config() -> Config:
    if _config is None:
        return configure()  # lazy: resolve from the environment on first use
    return _config
