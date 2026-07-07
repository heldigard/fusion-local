"""Machine-readable fusion-local capabilities."""

from __future__ import annotations

from typing import Any


def capabilities_payload(version: str) -> dict[str, Any]:
    """Return the stable capability manifest for orchestration consumers."""
    return {
        "command": "capabilities",
        "schema_version": 1,
        "tool": "fusion-local",
        "version": version,
        "capabilities": [
            {
                "name": "fuse",
                "purpose": (
                    "Run a bounded multi-model panel and judge into a "
                    "5-field analysis envelope."
                ),
                "read_only": True,
                "destructive": False,
                "idempotent": False,
                "open_world": True,
                "structured_json": True,
                "presets": ("subs", "payg", "cheap", "ultra", "mixed"),
                "cost": "variable",
            },
            {
                "name": "capabilities",
                "purpose": "Emit this local fusion capability manifest.",
                "read_only": True,
                "destructive": False,
                "idempotent": True,
                "open_world": False,
                "structured_json": True,
                "presets": tuple(),
                "cost": "cheap",
            },
            {
                "name": "openrouter",
                "purpose": (
                    "Delegate to the legacy hosted OpenRouter fusion path "
                    "when explicitly requested."
                ),
                "read_only": True,
                "destructive": False,
                "idempotent": False,
                "open_world": True,
                "structured_json": True,
                "presets": tuple(),
                "cost": "variable",
            },
        ],
        "health": {
            "cheap_llm_min_version": "1.1.1",
            "router_env": "FUSION_ROUTER",
            "current_model_envs": (
                "FUSION_CURRENT_MODEL",
                "CONTROLLER_MODEL",
                "CODEX_MODEL",
                "ANTHROPIC_MODEL",
                "GEMINI_MODEL",
                "QWEN_MODEL",
            ),
        },
    }
