"""Machine-readable fusion-local capabilities."""

from __future__ import annotations

import os
from typing import Any

from . import config
from ._version import __version__
from .judge import CHEAP_LLM_MIN_VERSION, preflight
from .panel import CURRENT_MODEL_ENV_KEYS, PANEL_PRESETS, PANEL_SUBS_ENV


def capabilities_payload() -> dict[str, Any]:
    """Return the stable capability manifest for orchestration consumers."""
    return {
        "command": "capabilities",
        "schema_version": 1,
        "tool": "fusion-local",
        "version": __version__,
        "capabilities": _capability_entries(),
        "health": _health_payload(),
    }


def _capability_entries() -> list[dict[str, Any]]:
    fuse_purpose = "Run a bounded multi-model panel and judge into a 5-field analysis envelope."
    openrouter_purpose = (
        "Delegate to the legacy hosted OpenRouter fusion path when explicitly requested."
    )
    caps_purpose = "Emit this local fusion capability manifest."
    return [
        _cap(
            "fuse",
            fuse_purpose,
            presets=PANEL_PRESETS,
            output_contracts={"default": "fusion-readable-v1", "json": "fusion-envelope-v1"},
        ),
        _cap(
            "capabilities",
            caps_purpose,
            idempotent=True,
            open_world=False,
            cost="cheap",
            output_contracts={"default": "capabilities-v1", "json": "capabilities-v1"},
        ),
        _cap(
            "openrouter",
            openrouter_purpose,
            output_contracts={
                "default": "openrouter-assistant-text",
                "json": "openrouter-chat-completion-v1",
            },
        ),
    ]


def _cap(name: str, purpose: str, **overrides: Any) -> dict[str, Any]:
    """One capability entry — every fusion command is read-only + structured.

    Defaults describe the deliberation commands (non-idempotent, open-world,
    variable cost); ``overrides`` adjusts per entry.
    """
    entry: dict[str, Any] = {
        "name": name,
        "purpose": purpose,
        "read_only": True,
        "destructive": False,
        "idempotent": False,
        "open_world": True,
        "structured_json": True,
        "output_contracts": {},
        "presets": (),
        "cost": "variable",
    }
    entry.update(overrides)
    return entry


def _health_payload() -> dict[str, Any]:
    """Static contract wiring + cheap live probes (all local, no network)."""
    return {
        "cheap_llm_min_version": CHEAP_LLM_MIN_VERSION,
        "router_env": "FUSION_ROUTER",
        "panel_subs_env": PANEL_SUBS_ENV,
        "current_model_envs": CURRENT_MODEL_ENV_KEYS,
        "live": _live_probes(),
    }


def _live_probes() -> dict[str, Any]:
    gate = preflight()
    return {
        "cheap_llm_ok": gate["ok"],
        "cheap_llm_version": gate["version"],
        "router_available": bool(config.ROUTER and config.ROUTER.exists()),
        "openrouter_key_present": bool(os.environ.get("OPENROUTER_API_KEY", "").strip()),
    }
