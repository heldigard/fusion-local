"""Canonical runtime version for every fusion-local entry point."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION_NAME = "fusion-local"


def resolve_version() -> str:
    """Return installed distribution metadata or an honest source-checkout fallback."""
    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "0+unknown"


__version__ = resolve_version()
