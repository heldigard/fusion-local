"""Current-controller-model detection and panel-seat exclusion.

One responsibility: identify the model the controller is running on (so the
panel does not echo it) and split a worker list into (run, skipped). Consumes
the catalog types/tables from ``panel_models``; independent of worker
execution (``panel``).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .panel_models import (
    MODEL_ALIASES,
    SUBS_WORKER_MODELS,
    LaneWorker,
    Worker,
)

CURRENT_MODEL_ENV_KEYS = (
    "FUSION_CURRENT_MODEL",
    "CONTROLLER_MODEL",
    "CODEX_MODEL",
    "ANTHROPIC_MODEL",
    "GEMINI_MODEL",
    "QWEN_MODEL",
)


def detect_current_model(explicit: str | None = None) -> str | None:
    """Best-effort current controller model for panel de-duplication."""
    if explicit and explicit.strip():
        return explicit.strip()
    identity = os.environ.get("CLAUDE_AGENT_IDENTITY", "").strip()
    if identity:
        model = _identity_model(identity)
        if model:
            return model
    for key in CURRENT_MODEL_ENV_KEYS:
        model = os.environ.get(key, "").strip()
        if model:
            return model
    # Inside a live Claude Code session none of the identity envs is exported;
    # settings.json holds the pinned controller model (e.g. claude-fable-5[1m]).
    # Without this fallback the ultra preset can seat the controller's own
    # model on the panel (echo-chamber seat).
    if os.environ.get("CLAUDECODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return _claude_settings_model()
    return None


def _claude_settings_model() -> str | None:
    settings = Path.home() / ".claude" / "settings.json"
    try:
        model = str(json.loads(settings.read_text(encoding="utf-8")).get("model") or "")
    except (OSError, json.JSONDecodeError):
        return None
    return model.strip() or None


def _identity_model(identity: str) -> str | None:
    try:
        payload = json.loads(identity)
    except json.JSONDecodeError:
        return _colon_identity_model(identity)
    if isinstance(payload, dict):
        model = payload.get("model")
        return model.strip() or None if isinstance(model, str) else None
    return _colon_identity_model(str(payload))


def _colon_identity_model(identity: str) -> str | None:
    parts = identity.split(":")
    if len(parts) >= 2 and parts[1].strip():
        return parts[1].strip()
    return None


def _normalize_name(value: str) -> str:
    # A terminal bracketed context-window suffix is not part of the model id.
    normalized = value.strip().lower().lstrip("~")
    return re.sub(r"\[[^\]]+\]$", "", normalized)


def _model_key(value: str) -> str:
    return "".join(ch for ch in _normalize_name(value) if ch.isalnum())


def _candidate_keys(names: Sequence[str]) -> set[str]:
    keys: set[str] = set()
    for name in names:
        if not name:
            continue
        keys.add(_model_key(name))
        for alias in MODEL_ALIASES.get(name, ()):
            keys.add(_model_key(alias))
        normalized = name.strip().lower().lstrip("~")
        for model, aliases in MODEL_ALIASES.items():
            if normalized == model.lstrip("~") or normalized in aliases:
                keys.add(_model_key(model))
                keys.update(_model_key(alias) for alias in aliases)
    return keys


def _worker_model_names(worker: Worker) -> tuple[str, ...]:
    if isinstance(worker, tuple):
        alias, _url, model, _key_env = worker
        return (alias, model)
    return (str(worker), *SUBS_WORKER_MODELS.get(str(worker), ()))


def _matches_current_model(worker: Worker, current_model: str | None) -> bool:
    if not current_model:
        return False
    current_keys = _candidate_keys((current_model,))
    worker_keys = _candidate_keys(_worker_model_names(worker))
    return bool(current_keys & worker_keys)


def _skip_current_result(worker: Worker, current_model: str) -> dict[str, Any]:
    if isinstance(worker, tuple):
        source = worker[0]
        lane = "payg"
    else:
        source = str(worker)
        lane = "subscription"
    return {
        "source": source,
        "lane": lane,
        "success": False,
        "skipped": True,
        "error": "skipped current controller model",
    }


def _without_current_model(
    workers: Sequence[LaneWorker], current_model: str | None
) -> tuple[list[LaneWorker], list[dict[str, Any]]]:
    if not current_model:
        return list(workers), []
    selected: list[LaneWorker] = []
    skipped: list[dict[str, Any]] = []
    for worker in workers:
        if _matches_current_model(worker, current_model):
            skipped.append(_skip_current_result(worker, current_model))
        else:
            selected.append(worker)
    return selected, skipped
