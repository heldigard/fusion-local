"""fusion-local — multi-model deliberation (5-field consensus output).

Public API:
    fuse(task, opts)      — panel → judge → 5-field envelope (main entry)
    panel(task, ...)      — gather N diverse model responses
    judge(task, results)  — synthesize panel into the 5-field schema
    main()                — console entry (``fusion-local``)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._version import __version__

if TYPE_CHECKING:  # static types for the lazy PEP 562 exports below
    from .cli import FuseOptions, fuse, main
    from .judge import DEFAULT_JUDGE_MODEL, FUSION_FIELDS, run_judge
    from .panel import run_panel, summarize

_EXPORTS = {
    "FuseOptions",
    "fuse",
    "main",
    "DEFAULT_JUDGE_MODEL",
    "FUSION_FIELDS",
    "run_judge",
    "run_panel",
    "summarize",
}


def __getattr__(name: str) -> Any:
    value: Any
    if name == "FuseOptions":
        from .cli import FuseOptions as value
    elif name == "fuse":
        from .cli import fuse as value
    elif name == "main":
        from .cli import main as value
    elif name == "DEFAULT_JUDGE_MODEL":
        from .judge import DEFAULT_JUDGE_MODEL as value
    elif name == "FUSION_FIELDS":
        from .judge import FUSION_FIELDS as value
    elif name == "run_judge":
        from .judge import run_judge as value
    elif name == "run_panel":
        from .panel import run_panel as value
    elif name == "summarize":
        from .panel import summarize as value
    else:
        raise AttributeError(f"module 'fusion' has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *_EXPORTS])


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
