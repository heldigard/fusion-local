"""Machine-readable fusion-local capabilities."""

from __future__ import annotations

import os
from typing import Any

from . import config
from ._boundary import MAX_EXTERNAL_RESPONSE_BYTES
from ._version import __version__
from .judge import CHEAP_LLM_MIN_VERSION, preflight
from .panel import (
    CREDIT_ONLY_WORKERS,
    CURRENT_MODEL_ENV_KEYS,
    PANEL_PAYG,
    PANEL_PRESETS,
    PANEL_SUBS,
    PANEL_SUBS_ENV,
    PANEL_SUBS_PROFILE_ENV,
    PAYG_PRESETS,
    SUBS_PROFILE_DEFAULT,
    SUBS_PROFILES,
)


def capabilities_payload() -> dict[str, Any]:
    """Return the stable capability manifest for orchestration consumers."""
    return {
        "command": "capabilities",
        "schema_version": 1,
        "tool": "fusion-local",
        "version": __version__,
        "field_semantics": {
            "structured_json": (
                "Deprecated alias for supports_json_output; it does not describe "
                "the default stdout format."
            )
        },
        "capabilities": _capability_entries(),
        "health": _health_payload(),
    }


# Envelope field set emitted by fuse() — the machine-consumed contract
# (cli-orchestration doctor treats this as the authoritative field list).
# Always present: schema_version, status, preset, the five analysis fields,
# judge_model, judge_valid, sources, panel_quorum, total_latency, total_known_cost.
# Conditional: error + panel_evidence (degraded); current_model (controller detected);
# subs_profile (subscription and mixed presets).
FUSE_ENVELOPE_FIELDS: tuple[str, ...] = (
    "schema_version",
    "status",
    "preset",
    "subs_profile",
    "consensus",
    "contradictions",
    "coverage_gaps",
    "unique_insights",
    "blind_spots",
    "judge_model",
    "judge_valid",
    "cost",
    "latency",
    "sources",
    "panel_quorum",
    "total_latency",
    "total_known_cost",
    "current_model",
    "error",
    "panel_evidence",
)


def _fuse_capability() -> dict[str, Any]:
    purpose = "Run a bounded multi-model panel and judge into a 5-field analysis envelope."
    return _cap(
        "fuse",
        purpose,
        presets=PANEL_PRESETS,
        invocation={
            "cli": "fusion-local [options] PROMPT",
            "python": "fusion.fuse(task, opts=None)",
        },
        inputs={
            "prompt": "non-empty string",
            "preset": list(PANEL_PRESETS),
            "timeout_seconds": "positive integer",
            "min_workers": "positive integer",
            "subs_profile": list(SUBS_PROFILES),
            "cloud_model": "pinned T2 judge fallback model",
            "cloud_judge": "boolean; skip local T1 judge when true",
        },
        output_contracts={"default": "fusion-readable-v1", "json": "fusion-envelope-v1"},
        default_output_format="text",
        output={"json_fields": list(FUSE_ENVELOPE_FIELDS)},
        preset_details=_preset_details(),
        prerequisites=[
            f"cheap_llm>={CHEAP_LLM_MIN_VERSION}",
            "available fail-closed prompt scrubber",
        ],
        exit_codes={"0": "strict judge result", "2": "degraded result or invalid usage"},
        recovery=(
            "On exit 2, inspect error and optional panel_evidence; do not treat the "
            "analysis fields as validated unless judge_valid is true."
        ),
    )


def _capabilities_capability() -> dict[str, Any]:
    return _cap(
        "capabilities",
        "Emit this local fusion capability manifest.",
        idempotent=True,
        open_world=False,
        cost="cheap",
        invocation={"cli": "fusion-local --capabilities"},
        inputs={},
        output_contracts={"default": "capabilities-v1", "json": "capabilities-v1"},
        default_output_format="json",
        output={"schema_version": 1},
        prerequisites=[],
        exit_codes={"0": "manifest emitted"},
        recovery="No external dispatch occurs; retry after correcting local runtime errors.",
    )


def _openrouter_capability() -> dict[str, Any]:
    return _cap(
        "openrouter",
        "Delegate to the legacy hosted OpenRouter fusion path when explicitly requested.",
        invocation={"cli": "fusion --openrouter [options] PROMPT"},
        inputs={
            "prompt": "non-empty string",
            "panel": "1-8 comma-separated model identifiers",
            "timeout_seconds": "positive integer",
            "max_tokens": "positive integer when provided",
        },
        output_contracts={
            "default": "openrouter-assistant-text",
            "json": "openrouter-chat-completion-v1",
        },
        default_output_format="text",
        output={"json_shape": "raw OpenRouter Chat Completion response"},
        prerequisites=["OPENROUTER_API_KEY", "available fail-closed prompt scrubber"],
        exit_codes={
            "0": "usable assistant response",
            "1": "missing key or unavailable prompt scrubber",
            "2": "invalid usage or operational/provider response failure",
        },
        recovery=(
            "Exit 1 requires local configuration. Exit 2 is safe to retry only when "
            "the operation is idempotent for the caller; stdout is empty on failure."
        ),
    )


def _capability_entries() -> list[dict[str, Any]]:
    return [_fuse_capability(), _capabilities_capability(), _openrouter_capability()]


def _cap(name: str, purpose: str, **overrides: Any) -> dict[str, Any]:
    """One capability entry — every fusion command is read-only and supports JSON.

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
        "supports_json_output": True,
        # Kept for schema-v1 consumers; see top-level field_semantics.
        "structured_json": True,
        "output_contracts": {},
        "presets": (),
        "cost": "variable",
    }
    entry.update(overrides)
    return entry


def _preset_details() -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {
        "subs": {
            "lanes": ["subscription", "payg-fallback"],
            "nominal_seats": len(PANEL_SUBS),
            "profile": SUBS_PROFILE_DEFAULT,
            "profiles": SUBS_PROFILES,
            "blocked_credit_modes": sorted(CREDIT_ONLY_WORKERS),
            "fallback": "default PAYG only when successful subscription seats are below quorum",
        },
        "mixed": {
            "lanes": ["subscription", "payg"],
            "nominal_seats": len(PANEL_SUBS) + len(PANEL_PAYG),
            "profile": SUBS_PROFILE_DEFAULT,
            "fallback": "none; both lanes always run",
        },
    }
    for name, specs in PAYG_PRESETS.items():
        details[name] = {
            "lanes": ["payg"],
            "nominal_seats": len(specs),
            "models": [spec[2] for spec in specs],
            "fallback": "none",
        }
    return details


def _health_payload() -> dict[str, Any]:
    """Static contract wiring + cheap live probes (all local, no network)."""
    return {
        "cheap_llm_min_version": CHEAP_LLM_MIN_VERSION,
        "router_env": "FUSION_ROUTER",
        "panel_subs_env": PANEL_SUBS_ENV,
        "panel_subs_profile_env": PANEL_SUBS_PROFILE_ENV,
        "router_protocol": "fusion-panel-v1",
        "judge_policy": "local-first by default; --cloud-judge selects pinned T2 directly",
        "max_external_response_bytes": MAX_EXTERNAL_RESPONSE_BYTES,
        "quorum": "final successful output count must satisfy min_workers before judging",
        "network_probed": False,
        "current_model_envs": CURRENT_MODEL_ENV_KEYS,
        "live": _live_probes(),
    }


def _live_probes() -> dict[str, Any]:
    gate = preflight()
    return {
        "cheap_llm_ok": gate["ok"],
        "cheap_llm_version": gate["version"],
        "router_available": bool(config.ROUTER and config.ROUTER.is_file()),
        "openrouter_key_present": bool(os.environ.get("OPENROUTER_API_KEY", "").strip()),
        "deepseek_key_present": bool(os.environ.get("DEEPSEEK_API_KEY", "").strip()),
        "deepinfra_key_present": bool(os.environ.get("DEEPINFRA_API_KEY", "").strip()),
        "zenmux_key_present": bool(os.environ.get("ZENMUX_API_KEY", "").strip()),
    }
