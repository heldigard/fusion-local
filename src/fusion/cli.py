"""CLI feature — entry point: ``main()`` + ``fuse()`` orchestration.

``main`` is the console-script entry (``fusion-local``). ``fuse`` wires the
panel feature to the judge feature and attaches sources/latency metadata.
``--openrouter`` early-delegates to ``fusion.delegate`` with all args intact.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

from .judge import DEFAULT_JUDGE_MODEL, run_judge
from .panel import detect_current_model, run_panel

try:  # version from installed metadata; fallback for editable/source runs
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("fusion-local")
except Exception:  # noqa: BLE001
    __version__ = "1.0.0"


@dataclass
class FuseOptions:
    """Tunable knobs for fuse() — a parameter object (keeps fuse() arity ≤ 5)."""

    preset: str = "subs"
    cloud_model: str | None = DEFAULT_JUDGE_MODEL
    panel_timeout: int = 60
    judge_timeout: int = 30
    min_workers: int = 2
    current_model: str | None = None


def fuse(task: str, opts: FuseOptions | None = None) -> dict[str, Any]:
    """Full fusion: panel → judge → 5-field envelope with sources metadata."""
    o = opts or FuseOptions()
    t0 = time.perf_counter()
    current_model = detect_current_model(o.current_model)
    pr = run_panel(
        task,
        preset=o.preset,
        timeout=o.panel_timeout,
        min_workers=o.min_workers,
        current_model=current_model,
    )
    jd = run_judge(task, pr, cloud_model=o.cloud_model, timeout=o.judge_timeout)
    jd["sources"] = [_source_meta(r) for r in pr]
    jd["total_latency"] = round(time.perf_counter() - t0, 2)
    jd["preset"] = o.preset
    if current_model:
        jd["current_model"] = current_model
    return jd


def _source_meta(r: dict[str, Any]) -> dict[str, Any]:
    """Project a panel result down to the sources-metadata shape."""
    meta: dict[str, Any] = {
        "source": r.get("source"),
        "lane": r.get("lane"),
        "success": bool(r.get("success")),
    }
    if not r.get("success") and r.get("error"):
        meta["error"] = r["error"]
    if r.get("skipped"):
        meta["skipped"] = True
    return meta


def _delegate_openrouter() -> int:
    """Delegate to the legacy OpenRouter fusion (opt-in via --openrouter).

    Strips --openrouter from argv so the legacy argparse sees the rest intact
    (--help/--panel/--json all work as if called directly).
    """
    sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != "--openrouter"]
    from . import delegate

    return delegate.main()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fusion-local",
        description="LOCAL multi-model deliberation — panel + judge, 5-field output.",
    )
    parser.add_argument("prompt", help="Question to deliberate on.")
    parser.add_argument("--version", action="version", version=f"fusion-local {__version__}")
    parser.add_argument(
        "--preset",
        choices=["subs", "payg", "cheap", "ultra", "mixed"],
        default="subs",
        help="Panel source: subs ($0 subs workers, default), payg, cheap, ultra, mixed.",
    )
    parser.add_argument(
        "--cloud-model",
        default=DEFAULT_JUDGE_MODEL,
        help=f"Judge model (default: {DEFAULT_JUDGE_MODEL}).",
    )
    parser.add_argument("--panel-timeout", type=int, default=60, help="Per-panelist timeout (s).")
    parser.add_argument("--judge-timeout", type=int, default=30, help="Judge call timeout (s).")
    parser.add_argument(
        "--min-workers",
        type=int,
        default=2,
        help="Min successful panelists before skipping PAYG fallback.",
    )
    parser.add_argument(
        "--current-model",
        help="Controller model to exclude from the panel (also detected from env when omitted).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the full 5-field envelope as JSON."
    )
    parser.add_argument(
        "--openrouter",
        action="store_true",
        help="Delegate to the legacy OpenRouter fusion instead of running locally.",
    )
    return parser


def _print_readable(envelope: dict[str, Any]) -> None:
    print("## Consensus")
    print(envelope.get("consensus") or "(none)")
    for key in ("contradictions", "coverage_gaps", "unique_insights", "blind_spots"):
        items = envelope.get(key, []) or []
        label = key.replace("_", " ").title()
        print(f"\n## {label}")
        if not items:
            print("(none)")
            continue
        for item in items:
            print(f"- {item}")
    sources = envelope.get("sources", [])
    ok = [s for s in sources if s.get("success")]
    print(
        f"\n## Meta\nJudge: {envelope.get('judge_model')} "
        f"(valid={envelope.get('judge_valid')}) | Panel OK: {len(ok)}/{len(sources)} "
        f"| latency: {envelope.get('total_latency')}s"
    )
    if envelope.get("error"):
        print(f"[warn] {envelope['error']}")
    evidence = envelope.get("panel_evidence") or []
    if evidence:
        print("\n## Panel Evidence")
        for item in evidence:
            source = item.get("source") or "unknown"
            lane = item.get("lane") or "?"
            suffix = "..." if item.get("truncated") else ""
            print(f"\n### {source} ({lane})")
            print(f"{item.get('output', '')}{suffix}")


def main() -> int:
    # Early delegation: --openrouter routes to the legacy OpenRouter fusion with
    # ALL args intact (legacy --help/--panel/--json work as if called directly).
    if "--openrouter" in sys.argv[1:]:
        return _delegate_openrouter()

    parser = _build_parser()
    args = parser.parse_args()
    if not args.prompt.strip():
        parser.error("prompt must not be empty")

    envelope = fuse(
        args.prompt,
        opts=FuseOptions(
            preset=args.preset,
            cloud_model=args.cloud_model,
            panel_timeout=args.panel_timeout,
            judge_timeout=args.judge_timeout,
            min_workers=args.min_workers,
            current_model=args.current_model,
        ),
    )

    if args.json:
        print(json.dumps(envelope, indent=2, ensure_ascii=False))
        return 0
    _print_readable(envelope)
    return 0 if envelope.get("judge_valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
