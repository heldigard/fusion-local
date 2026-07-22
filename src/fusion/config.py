"""Shared configuration for fusion-local (constants + env-driven cross-CLI wiring).

The cheap_llm bootstrap is a module-level side effect: importing ``fusion.config``
tries the installed ``cheap_llm`` package first, then inserts ``CHEAP_LLM_HOME`` on
``sys.path`` as a fallback. Idempotent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# --- cheap_llm bootstrap (judge transport + scrub + cache) ------------------
# Primary discovery is the EDITABLE INSTALL (pip install -e ~/cheap-llm) on
# site-packages — ``import cheap_llm`` resolves from any cwd without a path
# hack. The sys.path injection below is a FALLBACK, used only in a fresh
# checkout where the install hasn't run yet. This keeps fusion decoupled from
# the literal CHEAP_LLM_HOME path in the normal (installed) case.
CHEAP_LLM_HOME = Path(os.environ.get("CHEAP_LLM_HOME", str(Path.home() / "cheap-llm")))
try:
    import cheap_llm  # type: ignore[import-untyped]  # noqa: F401  — primary: editable install
except ImportError:
    if str(CHEAP_LLM_HOME) not in sys.path:
        sys.path.insert(0, str(CHEAP_LLM_HOME))

# --- Cross-CLI lane-1 router (subscription-worker dispatch) -----------------
# The default path lives under ~/.claude for historical compatibility, but the
# shim delegates to the CLI-agnostic cli-orchestration/cworker package. Codex,
# Antigravity, OpenCode, Kimi, and Qwen controllers should normally keep this
# default whenever the shared harness is installed. Set FUSION_ROUTER="" only
# to disable lane 1, then choose an explicit PAYG preset/flag if desired, or
# provide another compatible fusion-panel-v1 shim explicitly.
_env_router = os.environ.get("FUSION_ROUTER")
DEFAULT_ROUTER = Path.home() / ".claude" / "scripts" / "codex-worker-router.py"
# unset → shared harness default; "" → disable lane-1 (no implicit lane-2);
# "/path" → custom dispatch shim.
ROUTER: Path | None = (
    None if _env_router == "" else Path(_env_router) if _env_router else DEFAULT_ROUTER
)
