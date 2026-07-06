"""fusion-cli — multi-model deliberation (5-field consensus output).

Public API:
    fuse(task, opts)      — panel → judge → 5-field envelope (main entry)
    panel(task, ...)      — gather N diverse model responses
    judge(task, results)  — synthesize panel into the 5-field schema
    main()                — console entry (``fusion-local``)
"""

from __future__ import annotations

from .cli import FuseOptions, fuse, main
from .judge import DEFAULT_JUDGE_MODEL, FUSION_FIELDS, run_judge
from .panel import run_panel, summarize

__version__ = "1.0.0"

__all__ = [
    "FuseOptions",
    "fuse",
    "main",
    "DEFAULT_JUDGE_MODEL",
    "FUSION_FIELDS",
    "run_judge",
    "run_panel",
    "summarize",
    "__version__",
]
