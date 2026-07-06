"""Panel feature — gather N diverse model responses (lanes + orchestration).

Lane 1 ($0 subs): cworker router → codex-spark/agy35-flash/kimic/zai (Claude
ecosystem). Lane 2 (PAYG, universal cross-CLI): HTTP direct to OpenRouter. The
orchestration runs lane 1, falls back to lane 2 when fewer than ``min_workers``
succeed.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, TypeVar

from . import config

# Type alias for a lane-2 entry: (alias, url, model_name, api_key_env).
Spec = tuple[str, str, str, str]
Worker = TypeVar("Worker")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"

# Lane 1: $0 subscription workers, diverse families. Routed via config.ROUTER
# (codex=gpt-5.x, agy=gemini, kimic=kimi, zai=glm).
PANEL_SUBS: list[str] = ["codex-spark", "agy35-flash", "kimic", "zai"]

# Lane 2: PAYG fallback (HTTP direct, OpenRouter) — universal cross-CLI. PAYG
# stays strong but economical; cheap/ultra presets are explicit so the controller
# can pick cost vs depth intentionally.
PANEL_PAYG: list[tuple[str, str, str, str]] = [
    ("deepseek-v4-pro", OPENROUTER_URL, "deepseek/deepseek-v4-pro", OPENROUTER_KEY_ENV),
    ("qwen3.7-max", OPENROUTER_URL, "qwen/qwen3.7-max", OPENROUTER_KEY_ENV),
]

PANEL_CHEAP: list[tuple[str, str, str, str]] = [
    ("deepseek-v4-flash", OPENROUTER_URL, "deepseek/deepseek-v4-flash", OPENROUTER_KEY_ENV),
    ("qwen3.7-plus", OPENROUTER_URL, "qwen/qwen3.7-plus", OPENROUTER_KEY_ENV),
    ("minimax-m3", OPENROUTER_URL, "minimax/minimax-m3", OPENROUTER_KEY_ENV),
    ("mimo-v2.5-pro", OPENROUTER_URL, "xiaomi/mimo-v2.5-pro", OPENROUTER_KEY_ENV),
]

PANEL_ULTRA: list[tuple[str, str, str, str]] = [
    ("claude-fable-5", OPENROUTER_URL, "anthropic/claude-fable-5", OPENROUTER_KEY_ENV),
    ("claude-opus-4.8", OPENROUTER_URL, "anthropic/claude-opus-4.8", OPENROUTER_KEY_ENV),
    ("gpt-5.5-pro", OPENROUTER_URL, "openai/gpt-5.5-pro", OPENROUTER_KEY_ENV),
    ("gemini-pro-latest", OPENROUTER_URL, "~google/gemini-pro-latest", OPENROUTER_KEY_ENV),
]

PAYG_PRESETS: dict[str, list[Spec]] = {
    "payg": PANEL_PAYG,
    "cheap": PANEL_CHEAP,
    "ultra": PANEL_ULTRA,
}

SUBS_WORKER_MODELS: dict[str, tuple[str, ...]] = {
    "codex-spark": ("gpt-5.4", "openai/gpt-5.4"),
    "agy35-flash": ("gemini-3.5-flash", "google/gemini-3.5-flash"),
    "kimic": ("kimi-k2.7-code", "moonshotai/kimi-k2.7-code"),
    "zai": ("glm-5.2", "z-ai/glm-5.2"),
}

MODEL_ALIASES: dict[str, tuple[str, ...]] = {
    "~google/gemini-pro-latest": (
        "google/gemini-pro-latest",
        "google/gemini-3.5-pro",
        "gemini-pro-latest",
        "gemini-3.5-pro",
    ),
    "anthropic/claude-opus-4.8": ("claude-opus-4-8", "claude-opus-4.8"),
    "anthropic/claude-fable-5": ("claude-fable-5",),
    "openai/gpt-5.5-pro": ("gpt-5.5-pro",),
    "deepseek/deepseek-v4-pro": ("deepseek-v4-pro",),
    "deepseek/deepseek-v4-flash": ("deepseek-v4-flash",),
    "qwen/qwen3.7-max": ("qwen3.7-max", "qwen/qwen3.7-max"),
    "qwen/qwen3.7-plus": ("qwen3.7-plus", "qwen/qwen3.7-plus"),
    "minimax/minimax-m3": ("minimax-m3", "minimax-3"),
    "xiaomi/mimo-v2.5-pro": ("mimo-v2.5-pro", "mimo-2.5-pro"),
}

CURRENT_MODEL_ENV_KEYS = (
    "FUSION_CURRENT_MODEL",
    "CONTROLLER_MODEL",
    "CODEX_MODEL",
    "ANTHROPIC_MODEL",
    "GEMINI_MODEL",
    "QWEN_MODEL",
)

# Recursion guard — panelists answer directly, no tools / no delegation.
WORKER_GUARD = (
    "[FUSION_PANEL][NO_DELEGATE][NO_TOOLS]\n"
    "You are a deliberation panelist. Give your direct, reasoned answer to the TASK. "
    "Do NOT use tools, APIs, or further delegation. Text answer only.\n\nTASK:\n"
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
    return None


def _identity_model(identity: str) -> str | None:
    try:
        payload = json.loads(identity)
    except json.JSONDecodeError:
        return _colon_identity_model(identity)
    if isinstance(payload, dict):
        model = str(payload.get("model") or "").strip()
        return model or None
    return _colon_identity_model(str(payload))


def _colon_identity_model(identity: str) -> str | None:
    parts = identity.split(":")
    if len(parts) >= 2 and parts[1].strip():
        return parts[1].strip()
    return None


def _model_key(value: str) -> str:
    return "".join(ch for ch in value.strip().lower().lstrip("~") if ch.isalnum())


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
        "error": f"skipped current controller model ({current_model})",
    }


def _without_current_model(
    workers: Sequence[Worker], current_model: str | None
) -> tuple[list[Worker], list[dict[str, Any]]]:
    if not current_model:
        return list(workers), []
    selected: list[Worker] = []
    skipped: list[dict[str, Any]] = []
    for worker in workers:
        if _matches_current_model(worker, current_model):
            skipped.append(_skip_current_result(worker, current_model))
        else:
            selected.append(worker)
    return selected, skipped


def _payg_panel_for_preset(preset: str) -> list[Spec]:
    return PAYG_PRESETS.get(preset, PANEL_PAYG)


# --- Lane 1: cworker subprocess ($0 subscription workers) -------------------


def _cworker_worker(mode: str, task: str, timeout: int) -> dict[str, Any]:
    """Run one subscription worker via the codex-worker-router CLI (stdin prompt)."""
    if config.ROUTER is None or not config.ROUTER.exists():
        return {
            "source": mode,
            "lane": "subscription",
            "success": False,
            "error": "router unavailable (set FUSION_ROUTER or rely on lane-2)",
        }
    guarded = WORKER_GUARD + task
    try:
        proc = subprocess.run(
            ["python3", str(config.ROUTER), "--mode", mode, "--timeout", str(timeout)],
            input=guarded,
            capture_output=True,
            text=True,
            timeout=timeout + 15,
        )
    except subprocess.TimeoutExpired:
        return {"source": mode, "lane": "subscription", "success": False, "error": "timeout"}
    except FileNotFoundError as exc:
        return {
            "source": mode,
            "lane": "subscription",
            "success": False,
            "error": f"router missing: {exc}",
        }
    except Exception as exc:  # noqa: BLE001 — panel must not abort on one worker
        return {
            "source": mode,
            "lane": "subscription",
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    out = (proc.stdout or "").strip()
    if out:
        return {"source": mode, "lane": "subscription", "success": True, "output": out}
    return {
        "source": mode,
        "lane": "subscription",
        "success": False,
        "error": (proc.stderr or "").strip()[:300] or "empty output",
    }


# --- Lane 2: HTTP direct (PAYG, universal cross-CLI) ------------------------


def _http_worker(spec: Spec, task: str, timeout: int) -> dict[str, Any]:
    """Run one PAYG model via direct HTTP (OpenRouter openai-compat)."""
    alias, url, model, key_env = spec
    key = os.environ.get(key_env, "").strip()
    if not key:
        return {"source": alias, "lane": "payg", "success": False, "error": f"missing {key_env}"}
    guarded = WORKER_GUARD + task
    payload = json.dumps(
        {"model": model, "messages": [{"role": "user", "content": guarded}]}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://claude.local/fusion",
            "X-Title": "fusion",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        return {
            "source": alias,
            "lane": "payg",
            "success": False,
            "error": f"HTTP {exc.code}: {body}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "source": alias,
            "lane": "payg",
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    try:
        text = (result["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return {"source": alias, "lane": "payg", "success": False, "error": "malformed response"}
    if text:
        return {"source": alias, "lane": "payg", "success": True, "output": text}
    return {"source": alias, "lane": "payg", "success": False, "error": "empty content"}


# --- Orchestration ----------------------------------------------------------


def _worker_failure(worker: Any, error: BaseException) -> dict[str, Any]:
    if isinstance(worker, tuple) and worker:
        source = str(worker[0])
        lane = "payg"
    else:
        source = str(worker)
        lane = "subscription"
    return {
        "source": source,
        "lane": lane,
        "success": False,
        "error": f"{type(error).__name__}: {error}",
    }


def _run_lane(
    workers: Sequence[Worker],
    runner: Callable[[Worker, str, int], dict[str, Any]],
    task: str,
    timeout: int,
) -> list[dict[str, Any]]:
    """Fan out a lane in parallel. ``runner`` arity: (worker, task, timeout)."""
    if not workers:
        return []
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(len(workers), 8)) as pool:
        futs = {pool.submit(runner, w, task, timeout): w for w in workers}
        for fut in as_completed(futs):
            worker = futs[fut]
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001 — one worker must not abort the lane
                results.append(_worker_failure(worker, exc))
    return results


def _cworker_runner(mode: str, task: str, timeout: int) -> dict[str, Any]:
    return _cworker_worker(mode, task, timeout)


def _http_runner(spec: Spec, task: str, timeout: int) -> dict[str, Any]:
    return _http_worker(spec, task, timeout)


def run_panel(
    task: str,
    preset: str = "subs",
    timeout: int = 60,
    min_workers: int = 2,
    current_model: str | None = None,
) -> list[dict[str, Any]]:
    """Run the deliberation panel. Successful outputs first, failures after.

    preset:
      - "subs"  : lane 1 only ($0 subscription). Fallback to lane 2 if < min_workers succeed.
      - "payg"  : lane 2 only (universal PAYG HTTP direct).
      - "cheap" : low-cost OpenRouter lane 2 panel.
      - "ultra" : strongest verified OpenRouter lane 2 panel.
      - "mixed" : lane 1, then augment with lane 2 if needed.
    """
    preset = preset or "subs"
    current_model = detect_current_model(current_model)
    all_results: list[dict[str, Any]] = []
    if preset in ("subs", "mixed"):
        subs_workers, skipped = _without_current_model(PANEL_SUBS, current_model)
        all_results.extend(skipped)
        all_results.extend(_run_lane(subs_workers, _cworker_runner, task, timeout))
    ok = [r for r in all_results if r.get("success") and r.get("output")]
    if preset in PAYG_PRESETS or len(ok) < min_workers:
        payg_workers, skipped = _without_current_model(
            _payg_panel_for_preset(preset), current_model
        )
        all_results.extend(skipped)
        all_results.extend(_run_lane(payg_workers, _http_runner, task, timeout))
    ok = [r for r in all_results if r.get("success") and r.get("output")]
    return ok + [r for r in all_results if not r.get("success")]


def summarize(panel_results: list[dict[str, Any]]) -> str:
    """Render panel outputs as the labeled block the judge consumes."""
    parts: list[str] = []
    for r in panel_results:
        if r.get("output"):
            parts.append(f"--- {r['source']} ({r.get('lane', '?')}) ---\n{r['output']}")
    return "\n\n".join(parts)
