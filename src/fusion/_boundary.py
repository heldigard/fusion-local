"""Shared contracts for values and text crossing external boundaries."""

from __future__ import annotations

import argparse
from typing import Any

from . import config as _config  # noqa: F401 — bootstraps cheap_llm discovery

PUBLIC_ERROR_MAX_CHARS = 300
MAX_EXTERNAL_RESPONSE_BYTES = 4 * 1024 * 1024


class SecretScrubError(RuntimeError):
    """Raised when a fail-closed external prompt cannot be scrubbed."""


def public_error(code: str, safe_detail: Any = None) -> str:
    """Format trusted error metadata as one bounded public line."""
    message = " ".join(code.split())
    if safe_detail is not None:
        detail = " ".join(str(safe_detail).split())
        if detail:
            message = f"{message}: {detail}"
    return message[:PUBLIC_ERROR_MAX_CHARS]


def require_nonempty_string(name: str, value: Any, *, optional: bool = False) -> None:
    """Raise ValueError unless value is a non-blank string (or optional None)."""
    if optional and value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def require_positive_int(name: str, value: Any) -> None:
    """Raise ValueError unless value is a strict positive integer (not bool)."""
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def positive_int_arg(value: str) -> int:
    """argparse type for strict positive integers."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def nonempty_arg(value: str) -> str:
    """argparse type for non-blank strings."""
    if not value.strip():
        raise argparse.ArgumentTypeError("must be a non-empty string")
    return value


def scrub_external_text(text: str, *, fail_closed: bool) -> str:
    """Scrub secrets before third-party transport, optionally failing closed."""
    try:
        import cheap_llm  # type: ignore[import-untyped]

        scrubbed = cheap_llm.scrub_secrets(text)
        if not isinstance(scrubbed, str) or not scrubbed.strip():
            raise TypeError("scrubber returned unusable text")
        return scrubbed
    except Exception:  # noqa: BLE001 — policy below decides fail-open vs fail-closed
        if fail_closed:
            raise SecretScrubError("hosted prompt scrub unavailable") from None
        return text
