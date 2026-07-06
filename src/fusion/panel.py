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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from . import config

# Type alias for a lane-2 entry: (alias, url, model_name, api_key_env).
Spec = tuple[str, str, str, str]

# Lane 1: $0 subscription workers, diverse families. Routed via config.ROUTER
# (codex=gpt-5.x, agy=gemini, kimic=kimi, zai=glm).
PANEL_SUBS: list[str] = ["codex-spark", "agy35-flash", "kimic", "zai"]

# Lane 2: PAYG fallback (HTTP direct, OpenRouter) — universal cross-CLI.
# (alias, url, model_name, api_key_env)
PANEL_PAYG: list[tuple[str, str, str, str]] = [
    (
        "deepseek-reasoner",
        "https://openrouter.ai/api/v1/chat/completions",
        "deepseek/deepseek-reasoner",
        "OPENROUTER_API_KEY",
    ),
    (
        "or-qwenc-max",
        "https://openrouter.ai/api/v1/chat/completions",
        "qwen3.7-max",
        "OPENROUTER_API_KEY",
    ),
]

# Recursion guard — panelists answer directly, no tools / no delegation.
WORKER_GUARD = (
    "[FUSION_PANEL][NO_DELEGATE][NO_TOOLS]\n"
    "You are a deliberation panelist. Give your direct, reasoned answer to the TASK. "
    "Do NOT use tools, APIs, or further delegation. Text answer only.\n\nTASK:\n"
)


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


def _run_lane(workers: list, runner: Any, task: str, timeout: int) -> list[dict[str, Any]]:
    """Fan out a lane in parallel. ``runner`` arity: (worker, task, timeout)."""
    if not workers:
        return []
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(len(workers), 8)) as pool:
        futs = {pool.submit(runner, w, task, timeout): w for w in workers}
        for fut in as_completed(futs):
            results.append(fut.result())
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
) -> list[dict[str, Any]]:
    """Run the deliberation panel. Successful outputs first, failures after.

    preset:
      - "subs"  : lane 1 only ($0 subscription). Fallback to lane 2 if < min_workers succeed.
      - "payg"  : lane 2 only (universal PAYG HTTP direct).
      - "mixed" : lane 1, then augment with lane 2 if needed.
    """
    preset = preset or "subs"
    all_results: list[dict[str, Any]] = []
    if preset in ("subs", "mixed"):
        all_results.extend(_run_lane(PANEL_SUBS, _cworker_runner, task, timeout))
    ok = [r for r in all_results if r.get("success") and r.get("output")]
    if preset == "payg" or len(ok) < min_workers:
        all_results.extend(_run_lane(PANEL_PAYG, _http_runner, task, timeout))
    ok = [r for r in all_results if r.get("success") and r.get("output")]
    return ok + [r for r in all_results if not r.get("success")]


def summarize(panel_results: list[dict[str, Any]]) -> str:
    """Render panel outputs as the labeled block the judge consumes."""
    parts: list[str] = []
    for r in panel_results:
        if r.get("output"):
            parts.append(f"--- {r['source']} ({r.get('lane', '?')}) ---\n{r['output']}")
    return "\n\n".join(parts)
