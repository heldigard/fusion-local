"""Pytest bootstrap for fusion tests.

``fusion.config`` inserts ``CHEAP_LLM_HOME`` (default ``~/cheap-llm``) onto
``sys.path`` at import time, resolving ``~`` from ``$HOME``. Tests that patch
``cheap_llm.cheap_complete`` therefore break under a redirected ``HOME``
(CI sandboxes, hermetic-env sweeps). Resolve the real home via ``pwd`` —
immune to ``$HOME`` overrides — and prepend the sibling checkout if present.
"""

from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path

_real_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
for _candidate in (
    Path(os.environ.get("CHEAP_LLM_HOME", _real_home / "cheap-llm")),
    _real_home / "cheap-llm",
):
    if (_candidate / "cheap_llm.py").is_file() or (_candidate / "cheap_llm").is_dir():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break
