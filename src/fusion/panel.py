"""Panel feature — gather N diverse model responses (lanes + orchestration).

Lane 1 ($0 subs): cworker router → codex-spark/agy35-flash/kimic/zai (Claude
ecosystem). Lane 2 (PAYG, universal cross-CLI): HTTP direct to OpenRouter. The
orchestration runs lane 1, falls back to lane 2 when fewer than ``min_workers``
succeed.

The model catalog (``panel_models``) and current-controller-model detection
(``panel_current``) live in sibling modules; this module re-exports their
public names so ``from fusion.panel import X`` keeps working.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path  # noqa: F401 — re-exported (tests reach panel_mod.Path)
from typing import Any

from . import config
from ._boundary import (
    MAX_EXTERNAL_RESPONSE_BYTES,
    public_error,
    require_nonempty_string,
    require_positive_int,
    scrub_external_text,
)
from .panel_current import (  # noqa: F401 — re-exported (capabilities/tests)
    CURRENT_MODEL_ENV_KEYS,
    _matches_current_model,
    _without_current_model,
    detect_current_model,
)
from .panel_models import (  # noqa: F401 — re-exported (public/test surface)
    MODEL_ALIASES,
    OPENROUTER_KEY_ENV,
    OPENROUTER_URL,
    PANEL_CHEAP,
    PANEL_INTELLIGENCE,
    PANEL_PAYG,
    PANEL_PRESETS,
    PANEL_SUBS,
    PANEL_SUBS_ENV,
    PANEL_ULTRA,
    PAYG_PRESETS,
    SUBS_WORKER_MODELS,
    WORKER_GUARD,
    LaneWorker,
    Spec,
)


def _payg_panel_for_preset(preset: str) -> list[Spec]:
    if preset in ("subs", "mixed"):
        return PANEL_PAYG
    return PAYG_PRESETS[preset]


def _subs_workers() -> list[str]:
    """Lane-1 worker modes, honoring the FUSION_PANEL_SUBS cross-CLI override."""
    env = os.environ.get(PANEL_SUBS_ENV)
    if env is None:
        return list(PANEL_SUBS)
    return [mode.strip() for mode in env.split(",") if mode.strip()]


def _scrub(text: str) -> str:
    """Fail-closed secret scrub before fanning out to external models.

    The judge path scrubs unconditionally inside cheap_llm; panel workers are
    ALSO third parties, so scrub here too. A scrub failure must never degrade to
    sending the original text: direct ``run_panel`` callers receive
    ``SecretScrubError`` and ``fuse`` converts it to a safe degraded envelope.
    """
    return scrub_external_text(text, fail_closed=True)


# --- Lane 1: cworker subprocess ($0 subscription workers) -------------------


def _cworker_build_command(mode: str, timeout: int) -> list[str]:
    """Router argv with the versioned fusion-panel-v1 protocol.

    The protocol makes stdout answer-only and disables the router's own PAYG
    fallback — Fusion exclusively owns lane-2/cost policy.
    """
    return [
        "python3",
        str(config.ROUTER),
        "--mode",
        mode,
        "--timeout",
        str(timeout),
        "--protocol",
        "fusion-panel-v1",
    ]


def _cworker_parse(
    proc: subprocess.CompletedProcess[Any], raw_stdout: bytes, mode: str
) -> dict[str, Any]:
    """Reduce a router process + captured stdout to a panel result dict.

    Prefers ``proc.stdout`` (set by test mocks) over the tempfile capture, so a
    mocked ``subprocess.run`` returning a ``CompletedProcess`` still works.
    """
    mocked_stdout = getattr(proc, "stdout", None)
    if isinstance(mocked_stdout, str):
        raw_stdout = mocked_stdout.encode("utf-8")
    elif isinstance(mocked_stdout, bytes):
        raw_stdout = mocked_stdout
    if len(raw_stdout) > MAX_EXTERNAL_RESPONSE_BYTES:
        return {
            "source": mode,
            "lane": "subscription",
            "success": False,
            "error": "router response too large",
        }
    try:
        out = raw_stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        return {
            "source": mode,
            "lane": "subscription",
            "success": False,
            "error": "router returned malformed output",
        }
    if proc.returncode != 0:
        return {
            "source": mode,
            "lane": "subscription",
            "success": False,
            "error": public_error(f"router exited with status {proc.returncode}"),
        }
    if out:
        return {"source": mode, "lane": "subscription", "success": True, "output": out}
    return {
        "source": mode,
        "lane": "subscription",
        "success": False,
        "error": "router returned empty output",
    }


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
    command = _cworker_build_command(mode, timeout)
    try:
        # Do not use capture_output: a misbehaving router could otherwise fill
        # memory before Fusion gets a chance to enforce its response limit.
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            proc = subprocess.run(
                command,
                input=guarded.encode("utf-8"),
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=timeout + 15,
            )
            stdout_file.seek(0)
            raw_stdout = stdout_file.read(MAX_EXTERNAL_RESPONSE_BYTES + 1)
    except subprocess.TimeoutExpired:
        return {"source": mode, "lane": "subscription", "success": False, "error": "timeout"}
    except FileNotFoundError as exc:
        return {
            "source": mode,
            "lane": "subscription",
            "success": False,
            "error": public_error("router missing", type(exc).__name__),
        }
    except Exception as exc:  # noqa: BLE001 — panel must not abort on one worker
        return {
            "source": mode,
            "lane": "subscription",
            "success": False,
            "error": public_error("router failure", type(exc).__name__),
        }
    return _cworker_parse(proc, raw_stdout, mode)


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
        # PAYG URLs come from fixed preset specs in this module, not user input.
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosemgrep
            raw = resp.read(MAX_EXTERNAL_RESPONSE_BYTES + 1)
        if not isinstance(raw, bytes):
            raise TypeError("invalid response bytes")
        if len(raw) > MAX_EXTERNAL_RESPONSE_BYTES:
            return {
                "source": alias,
                "lane": "payg",
                "success": False,
                "error": "payg response too large",
            }
        result = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {
            "source": alias,
            "lane": "payg",
            "success": False,
            "error": public_error("payg HTTP error", exc.code),
        }
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return {
            "source": alias,
            "lane": "payg",
            "success": False,
            "error": "malformed response",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "source": alias,
            "lane": "payg",
            "success": False,
            "error": public_error("payg transport error", type(exc).__name__),
        }
    return _http_parse_response(result, alias, model)


def _safe_usage(value: Any) -> dict[str, int | float]:
    """Allowlist numeric provider usage fields; never retain arbitrary response data."""
    if not isinstance(value, dict):
        return {}
    safe: dict[str, int | float] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost"):
        metric = value.get(key)
        if isinstance(metric, (int, float)) and not isinstance(metric, bool) and metric >= 0:
            safe[key] = metric
    return safe


def _http_parse_response(result: dict[str, Any], alias: str, model: str) -> dict[str, Any]:
    """Extract assistant text + safe metadata from a parsed provider response."""
    try:
        choice = result["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {"source": alias, "lane": "payg", "success": False, "error": "malformed response"}
    if not isinstance(content, str):
        return {"source": alias, "lane": "payg", "success": False, "error": "malformed response"}
    text = content.strip()
    if not text:
        return {"source": alias, "lane": "payg", "success": False, "error": "empty content"}
    output: dict[str, Any] = {
        "source": alias,
        "lane": "payg",
        "success": True,
        "output": text,
        "model": result.get("model") if isinstance(result.get("model"), str) else model,
    }
    finish_reason = choice.get("finish_reason")
    if isinstance(finish_reason, str):
        output["finish_reason"] = finish_reason
    usage = _safe_usage(result.get("usage"))
    if usage:
        output["usage"] = usage
    return output


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
        "error": public_error("worker failure", type(error).__name__),
    }


def _run_lane(
    workers: Sequence[LaneWorker],
    runner: Callable[[LaneWorker, str, int], dict[str, Any]],
    task: str,
    timeout: int,
) -> list[dict[str, Any]]:
    """Fan out a lane in parallel. ``runner`` arity: (worker, task, timeout)."""
    if not workers:
        return []
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(len(workers), 8)) as pool:
        futs = {pool.submit(runner, w, task, timeout): w for w in workers}
        started = {future: time.monotonic() for future in futs}
        for fut in as_completed(futs):
            worker = futs[fut]
            try:
                result = fut.result()
            except Exception as exc:  # noqa: BLE001 — one worker must not abort the lane
                result = _worker_failure(worker, exc)
            if not isinstance(result, dict):
                result = _worker_failure(worker, TypeError("invalid worker result"))
            result.setdefault("duration_seconds", round(time.monotonic() - started[fut], 3))
            results.append(result)
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
      - "subs"        : lane 1 only ($0 subscription). Fallback to lane 2 if < min_workers succeed.
      - "payg"        : lane 2 only (universal PAYG HTTP direct).
      - "cheap"       : low-cost OpenRouter lane 2 panel.
      - "intelligence": frontier-accessible lane 2 panel (no premium $25-50/M seats).
      - "ultra"       : strongest verified OpenRouter lane 2 panel (full frontier).
      - "mixed"       : always run lane 1 and the default PAYG lane 2 panel.
    """
    require_nonempty_string("task", task)
    if preset not in PANEL_PRESETS:
        raise ValueError(f"preset must be one of: {', '.join(PANEL_PRESETS)}")
    require_positive_int("timeout", timeout)
    require_positive_int("min_workers", min_workers)
    require_nonempty_string("current_model", current_model, optional=True)
    task = _scrub(task)
    current_model = detect_current_model(current_model)

    # "mixed" always runs BOTH lanes. They are independent (no shared mutable
    # state, disjoint worker sets), so run them concurrently instead of waiting
    # for lane 1 to finish before starting lane 2 — removes the sequential lane-2
    # latency from the only preset that unconditionally pays for both. Result
    # order stays deterministic: skips, then subscription outputs, then payg
    # outputs, finally reordered success-first by the shared return path.
    if preset == "mixed":
        subs_workers, skip_subs = _without_current_model(_subs_workers(), current_model)
        payg_workers, skip_payg = _without_current_model(
            _payg_panel_for_preset(preset), current_model
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_subs = pool.submit(_run_lane, subs_workers, _cworker_runner, task, timeout)
            fut_payg = pool.submit(_run_lane, payg_workers, _http_runner, task, timeout)
            mixed_results = [*skip_subs, *skip_payg, *fut_subs.result(), *fut_payg.result()]
        ok = [r for r in mixed_results if r.get("success") and r.get("output")]
        return ok + [r for r in mixed_results if not r.get("success")]

    all_results: list[dict[str, Any]] = []
    if preset == "subs":
        subs_workers, skipped = _without_current_model(_subs_workers(), current_model)
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
