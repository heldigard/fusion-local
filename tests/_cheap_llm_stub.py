"""Minimal ``cheap_llm`` stand-in for hermetic environments (CI runners).

Tests patch ``cheap_llm.cheap_complete`` / ``cheap_llm.scrub_secrets`` by module
path, which requires the module to be importable even when every call is
mocked. Outside a dev checkout (GitHub Actions) the sibling ``~/cheap-llm``
repo does not exist, so ``fusion.config``'s path bootstrap finds nothing and
every ``patch("cheap_llm...")`` fails with ModuleNotFoundError.

This stub provides ONLY the contract surface fusion touches, so the real
package is used whenever it is installed and the stub is installed strictly as
a fallback. It is test scaffolding, not a judge transport: an unpatched
``cheap_complete`` raises, which ``run_judge`` converts into the normal
degraded envelope.
"""

from __future__ import annotations

import sys
import types
from typing import Any

_STUB_VERSION = "1.4.0"  # >= fusion.judge.CHEAP_LLM_MIN_VERSION


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in value.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _require(min_version: str) -> str:
    if _version_tuple(_STUB_VERSION) < _version_tuple(min_version):
        raise RuntimeError(f"cheap_llm stub {_STUB_VERSION} < required {min_version}")
    return _STUB_VERSION


def _scrub_secrets(text: str) -> str:
    # Identity passthrough: tests that exercise scrub behavior patch this.
    return text


def _cheap_complete(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise RuntimeError("cheap_llm stub: no judge transport (tests must patch cheap_complete)")


def install_stub() -> None:
    """Register the stub in sys.modules unless cheap_llm already resolves."""
    if "cheap_llm" in sys.modules:
        return
    module = types.ModuleType("cheap_llm")
    module.__version__ = _STUB_VERSION  # type: ignore[attr-defined]
    module.require = _require  # type: ignore[attr-defined]
    module.scrub_secrets = _scrub_secrets  # type: ignore[attr-defined]
    module.cheap_complete = _cheap_complete  # type: ignore[attr-defined]
    module.__doc__ = "Test stub for hermetic CI; real cheap_llm is preferred when installed."
    sys.modules["cheap_llm"] = module
