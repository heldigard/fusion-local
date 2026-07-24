"""CLI feature — entry point: ``main()`` + ``fuse()`` orchestration.

``main`` is the console-script entry (``fusion-local``). ``fuse`` wires the
panel feature to the judge feature and attaches sources/latency metadata.
``--openrouter`` early-delegates to ``fusion.delegate`` with all args intact.
"""

# vs-soft-allow — fuse() is one cohesive orchestration pipeline (validate →
# preflight → panel → judge → attach envelope metadata); its length is defensive
# metadata/quorum/cost wiring, not mixed responsibilities. Splitting would hurt
# clarity without separating concerns.

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

from ._boundary import (
    SecretScrubError,
    nonempty_arg,
    positive_int_arg,
    require_nonempty_string,
    require_positive_int,
)
from ._version import __version__
from .capabilities import capabilities_payload
from .judge import DEFAULT_JUDGE_MODEL, STRONG_JUDGE_MODEL, empty_fields, preflight, run_judge
from .panel import (
    PANEL_PRESETS,
    SUBS_PROFILE_DEFAULT,
    SUBS_PROFILE_NAMES,
    detect_current_model,
    invocation_subs_profile,
    panel_seat_status,
    run_panel,
)

# Presets whose panel seats are frontier models. Their judge scales up too:
# a local 4B judge cannot faithfully synthesize frontier deliberation, so these
# presets default to the strong cloud judge (STRONG_JUDGE_MODEL) directly,
# skipping the local T1 tier. Explicit option values override inference;
# --cloud-judge forces cloud-only judging on presets that are local-first.
STRONG_JUDGE_PRESETS: tuple[str, ...] = ("intelligence", "ultra")


@dataclass
class FuseOptions:
    """Tunable knobs for fuse() — a parameter object (keeps fuse() arity ≤ 5)."""

    preset: str = "subs"
    # None = scale by preset (STRONG_JUDGE_MODEL for STRONG_JUDGE_PRESETS,
    # DEFAULT_JUDGE_MODEL otherwise). An explicit value always wins.
    cloud_model: str | None = None
    # Reasoning-tier seats (Opus/Kimi/GLM/Grok/Sol) legitimately run 60-120s;
    # the prior 60s default starved them and dropped quorum. Fast seats are
    # capped separately in panel._seat_timeout so flash/haiku still fail fast.
    panel_timeout: int = 120
    # Covers cold T1 local (~25s) + one T2 cloud attempt (~18s); 30s starved
    # T2 after a cold local miss and failed the judge after a good panel.
    judge_timeout: int = 45
    min_workers: int = 2
    current_model: str | None = None
    # None = scale by preset (cloud-only judge for STRONG_JUDGE_PRESETS,
    # local-first otherwise). An explicit value (e.g. --cloud-judge) wins.
    judge_prefer_local: bool | None = None
    subs_profile: str | None = None
    allow_payg_fallback: bool = False


def fuse(task: str, opts: FuseOptions | None = None) -> dict[str, Any]:
    """Full fusion: panel → judge → 5-field envelope with sources metadata."""
    require_nonempty_string("task", task)
    if opts is not None and not isinstance(opts, FuseOptions):
        raise ValueError("opts must be a FuseOptions instance")
    o = opts or FuseOptions()
    if o.preset not in PANEL_PRESETS:
        raise ValueError(f"preset must be one of: {', '.join(PANEL_PRESETS)}")
    require_nonempty_string("cloud_model", o.cloud_model, optional=True)
    require_nonempty_string("current_model", o.current_model, optional=True)
    require_nonempty_string("subs_profile", o.subs_profile, optional=True)
    resolved_subs_profile = invocation_subs_profile(o.preset, o.subs_profile)
    require_positive_int("panel_timeout", o.panel_timeout)
    require_positive_int("judge_timeout", o.judge_timeout)
    require_positive_int("min_workers", o.min_workers)
    if o.judge_prefer_local is not None and not isinstance(o.judge_prefer_local, bool):
        raise ValueError("judge_prefer_local must be a boolean or None")
    if not isinstance(o.allow_payg_fallback, bool):
        raise ValueError("allow_payg_fallback must be a boolean")
    # Per-preset judge scaling: frontier panels default to the strong cloud
    # judge (cloud-only); cheaper presets keep the local-first flash judge.
    # Explicit overrides (cloud_model, judge_prefer_local, --cloud-judge) win.
    strong_judge = o.preset in STRONG_JUDGE_PRESETS
    judge_model = o.cloud_model or (STRONG_JUDGE_MODEL if strong_judge else DEFAULT_JUDGE_MODEL)
    judge_prefer_local = (
        o.judge_prefer_local if o.judge_prefer_local is not None else not strong_judge
    )
    t0 = time.perf_counter()
    # Judge-transport preflight BEFORE the panel: a missing/drifted cheap_llm
    # must fail before PAYG/subscription spend, not after the panel already ran.
    gate = preflight()
    if not gate["ok"]:
        return empty_fields(
            schema_version=1,
            status="degraded",
            judge_model=None,
            judge_valid=False,
            error=gate["error"],
            sources=[],
            preset=o.preset,
            **({"subs_profile": resolved_subs_profile} if o.preset in ("subs", "mixed") else {}),
            panel_quorum={"required": o.min_workers, "successful": 0, "met": False},
            total_latency=round(time.perf_counter() - t0, 2),
        )
    current_model = detect_current_model(o.current_model)
    try:
        pr = run_panel(
            task,
            preset=o.preset,
            timeout=o.panel_timeout,
            min_workers=o.min_workers,
            current_model=current_model,
            subs_profile=o.subs_profile,
            allow_payg_fallback=o.allow_payg_fallback,
        )
    except SecretScrubError:
        return empty_fields(
            schema_version=1,
            status="degraded",
            judge_model=None,
            judge_valid=False,
            error="panel prompt scrub unavailable",
            sources=[],
            preset=o.preset,
            **({"subs_profile": resolved_subs_profile} if o.preset in ("subs", "mixed") else {}),
            panel_quorum={"required": o.min_workers, "successful": 0, "met": False},
            total_latency=round(time.perf_counter() - t0, 2),
        )
    successful = sum(bool(r.get("success") and r.get("output")) for r in pr)
    jd = run_judge(
        task,
        pr,
        cloud_model=judge_model,
        timeout=o.judge_timeout,
        min_outputs=o.min_workers,
        prefer_local=judge_prefer_local,
        # Selecting a metered preset explicitly authorizes a metered judge
        # fallback. The default subscription preset requires the opt-in flag.
        allow_cloud_fallback=o.allow_payg_fallback or o.preset != "subs",
    )
    jd["sources"] = [_source_meta(r) for r in pr]
    jd["total_latency"] = round(time.perf_counter() - t0, 2)
    jd["preset"] = o.preset
    if o.preset in ("subs", "mixed"):
        jd["subs_profile"] = resolved_subs_profile
    jd["schema_version"] = 1
    jd["status"] = "ok" if jd.get("judge_valid") else "degraded"
    jd["panel_quorum"] = {
        "required": o.min_workers,
        "successful": successful,
        "met": successful >= o.min_workers,
        # Per-seat outcome lets the controller distinguish a timeout wall
        # (several "timed_out") from genuine model disagreement on quorum loss.
        "seats": panel_seat_status(pr),
    }
    panel_cost = sum(
        float(r.get("usage", {}).get("cost", 0))
        for r in pr
        if isinstance(r.get("usage"), dict)
        and isinstance(r.get("usage", {}).get("cost", 0), (int, float))
    )
    # total_known_cost is an always-present envelope field (see capabilities
    # FUSE_ENVELOPE_FIELDS). A degraded judge may omit cost or return a
    # non-numeric value; default it to 0.0 so the field is emitted regardless.
    judge_cost = jd.get("cost", 0)
    safe_judge_cost = (
        float(judge_cost)
        if isinstance(judge_cost, (int, float)) and not isinstance(judge_cost, bool)
        else 0.0
    )
    jd["total_known_cost"] = panel_cost + safe_judge_cost
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
    if isinstance(r.get("duration_seconds"), (int, float)):
        meta["duration_seconds"] = r["duration_seconds"]
    if isinstance(r.get("model"), str):
        meta["model"] = r["model"]
    if isinstance(r.get("finish_reason"), str):
        meta["finish_reason"] = r["finish_reason"]
    if isinstance(r.get("usage"), dict):
        meta["usage"] = r["usage"]
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
    parser.add_argument("prompt", nargs="?", help="Question to deliberate on.")
    parser.add_argument("--version", action="version", version=f"fusion-local {__version__}")
    parser.add_argument(
        "--preset",
        choices=PANEL_PRESETS,
        default="subs",
        help="Panel source: subs ($0, default), payg, cheap, intelligence, ultra, mixed.",
    )
    parser.add_argument(
        "--subs-profile",
        choices=SUBS_PROFILE_NAMES,
        default=None,
        help=(
            "Subscription hands: balanced, coding, reasoning, fast, or specialists. "
            f"Default: {SUBS_PROFILE_DEFAULT} (or FUSION_SUBS_PROFILE)."
        ),
    )
    parser.add_argument(
        "--cloud-model",
        type=nonempty_arg,
        default=None,
        help=(
            "Pinned T2 judge model used only after explicit metered authority "
            f"(default: {STRONG_JUDGE_MODEL} for ultra/intelligence, "
            f"{DEFAULT_JUDGE_MODEL} otherwise)."
        ),
    )
    parser.add_argument(
        "--cloud-judge",
        action="store_true",
        help="Skip the local T1 judge and use the pinned T2 cloud judge directly.",
    )
    parser.add_argument(
        "--panel-timeout",
        type=positive_int_arg,
        default=120,
        help="Per-panelist timeout (s); fast-tier seats are internally capped.",
    )
    parser.add_argument(
        "--judge-timeout",
        type=positive_int_arg,
        default=45,
        help="Judge call timeout (s); default covers cold local + one cloud attempt.",
    )
    parser.add_argument(
        "--min-workers",
        type=positive_int_arg,
        default=2,
        help="Required successful panelists before judging.",
    )
    parser.add_argument(
        "--allow-payg-fallback",
        action="store_true",
        help=(
            "Allow the subscription preset to use PAYG panel/judge fallback when "
            "subscription quorum or the local judge fails."
        ),
    )
    parser.add_argument(
        "--current-model",
        type=nonempty_arg,
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
    parser.add_argument(
        "--capabilities",
        action="store_true",
        help="Emit machine-readable local fusion capability metadata.",
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
    attempted = [s for s in sources if not s.get("skipped")]
    skipped = [s for s in sources if s.get("skipped")]
    print(
        f"\n## Meta\nJudge: {envelope.get('judge_model')} "
        f"(valid={envelope.get('judge_valid')}) | Panel OK: {len(ok)}/{len(attempted)} "
        f"| skipped: {len(skipped)} "
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
    if args.capabilities:
        print(json.dumps(capabilities_payload(), indent=2, ensure_ascii=False))
        return 0
    if not (args.prompt or "").strip():
        parser.error("prompt must not be empty")

    try:
        envelope = fuse(
            args.prompt,
            opts=FuseOptions(
                preset=args.preset,
                cloud_model=args.cloud_model,
                panel_timeout=args.panel_timeout,
                judge_timeout=args.judge_timeout,
                min_workers=args.min_workers,
                current_model=args.current_model,
                judge_prefer_local=False if args.cloud_judge else None,
                subs_profile=args.subs_profile,
                allow_payg_fallback=args.allow_payg_fallback,
            ),
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.json:
        print(json.dumps(envelope, indent=2, ensure_ascii=False))
    else:
        _print_readable(envelope)
    # Same exit contract in both output modes: 0 = valid 5-field synthesis,
    # 2 = degraded (judge invalid/unavailable) — orchestrators can gate on it.
    return 0 if envelope.get("judge_valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
