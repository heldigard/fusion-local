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
    import cheap_llm  # noqa: F401  — primary: editable install
except ImportError:
    if str(CHEAP_LLM_HOME) not in sys.path:
        sys.path.insert(0, str(CHEAP_LLM_HOME))

# --- Cross-CLI lane-1 router (subscription-worker dispatch) -----------------
# Default points at the Claude-ecosystem codex-worker-router. Non-Claude CLIs
# (Codex / Antigravity / OpenCode) can either:
#   - point FUSION_ROUTER at their own dispatch shim, or
#   - set FUSION_ROUTER="" to disable lane-1; the panel then falls back to
#     lane-2 (PAYG HTTP direct), which is universal.
_env_router = os.environ.get("FUSION_ROUTER")
DEFAULT_ROUTER = Path.home() / ".claude" / "scripts" / "codex-worker-router.py"
# unset → Claude ecosystem default; "" → disable lane-1 (panel falls back to lane-2);
# "/path" → custom dispatch shim.
ROUTER: Path | None = (
    None if _env_router == "" else Path(_env_router) if _env_router else DEFAULT_ROUTER
)
