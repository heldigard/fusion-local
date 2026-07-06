#!/usr/bin/env python3
"""Regression tests for the ``fusion`` package — panel, judge, fuse, CLI.

Imports from the installed ``fusion`` package (pip install -e .). All network
paths (cworker subprocess, HTTP, cheap_llm) are mocked — fully offline.

Run: python3 tests/test_fusion.py
"""

from __future__ import annotations

import io
import json
import sys
from unittest.mock import patch

import fusion.cli as fcli
import fusion.judge as judge_mod
import fusion.panel as panel_mod
from fusion import FuseOptions, fuse

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}" if detail else name)


# === panel feature ==========================================================


def test_panel_payg_uses_lane2_only() -> None:
    calls: list[str] = []

    def fake_http(spec, task, timeout):
        calls.append(f"http:{spec[0]}")
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    def fake_cworker(mode, task, timeout):
        calls.append(f"cw:{mode}")
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    with (
        patch.object(panel_mod, "_http_worker", fake_http),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
    ):
        res = panel_mod.run_panel("task", preset="payg")
    ok = [r for r in res if r["success"]]
    check(
        "payg preset → lane2 only",
        len(ok) == 2 and not any(c.startswith("cw") for c in calls),
        str(calls),
    )


def test_panel_subs_falls_back_to_payg() -> None:
    def fake_cworker(mode, task, timeout):
        ok = mode == "codex-spark"
        return {
            "source": mode,
            "lane": "subscription",
            "success": ok,
            "output": "o" if ok else None,
            "error": None if ok else "no quota",
        }

    http_called: list[str] = []

    def fake_http(spec, task, timeout):
        http_called.append(spec[0])
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with (
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        panel_mod.run_panel("task", preset="subs", min_workers=2)
    check("subs fallback ran lane2", len(http_called) == 2, str(http_called))


def test_panel_summarize() -> None:
    pr = [
        {"source": "a", "lane": "subscription", "output": "alpha"},
        {"source": "b", "lane": "payg", "success": False, "error": "x"},
    ]
    s = panel_mod.summarize(pr)
    check("summarize includes ok source", "a" in s and "alpha" in s)
    check("summarize excludes failed", "error" not in s.lower())


def test_cworker_router_unavailable() -> None:
    # When ROUTER is None (FUSION_ROUTER=""), _cworker_worker returns graceful error.
    with patch.object(panel_mod.config, "ROUTER", None):
        res = panel_mod._cworker_worker("codex-spark", "task", 5)
    check(
        "router None → graceful fail",
        res["success"] is False and "router" in res["error"],
        res["error"],
    )


# === judge feature ==========================================================


def _fake_cheap_complete(envelope: dict, *, json_valid: bool = True, text: str | None = None):
    payload = {
        "text": text if text is not None else json.dumps(envelope),
        "model": "deepseek/deepseek-v4-flash",
        "tier": "T2",
        "latency": 1.0,
        "cost": 0.0,
        "json_valid": json_valid,
        "fields_ok": json_valid,
        "attempts": [],
        "error": None if json_valid else "invalid",
    }
    return lambda system, prompt, **kw: payload


def test_judge_parses_5field() -> None:
    env = {
        "consensus": "C",
        "contradictions": ["d"],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }
    with patch("cheap_llm.cheap_complete", _fake_cheap_complete(env)):
        jd = judge_mod.run_judge("task", [{"source": "x", "output": "y"}])
    check("judge valid", jd["judge_valid"] is True)
    check("consensus parsed", jd["consensus"] == "C")
    check("contradictions list", jd["contradictions"] == ["d"])


def test_judge_graceful_on_invalid_json() -> None:
    with patch(
        "cheap_llm.cheap_complete", _fake_cheap_complete({}, json_valid=False, text="raw prose")
    ):
        jd = judge_mod.run_judge("task", [{"source": "x", "output": "y"}])
    check("invalid → judge_valid False", jd["judge_valid"] is False)
    check("raw parked in consensus", jd["consensus"] == "raw prose")


def test_judge_coerces_string_to_list() -> None:
    env = {
        "consensus": "c",
        "contradictions": "should be list",
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }
    with patch("cheap_llm.cheap_complete", _fake_cheap_complete(env)):
        jd = judge_mod.run_judge("task", [{"source": "x", "output": "y"}])
    check("string coerced", jd["contradictions"] == ["should be list"], str(jd["contradictions"]))


def test_judge_empty_panel() -> None:
    jd = judge_mod.run_judge("task", [])
    check("empty panel → invalid", jd["judge_valid"] is False)
    check("empty panel → error", "no panel" in (jd.get("error") or ""))


# === fuse + cli =============================================================


def test_fuse_integrates() -> None:
    with (
        patch.object(
            panel_mod,
            "_cworker_worker",
            lambda m, t, to: {"source": m, "lane": "subscription", "success": True, "output": "o"},
        ),
        patch(
            "cheap_llm.cheap_complete",
            _fake_cheap_complete(
                {
                    "consensus": "C",
                    "contradictions": [],
                    "coverage_gaps": [],
                    "unique_insights": [],
                    "blind_spots": [],
                }
            ),
        ),
    ):
        out = fuse("task", opts=FuseOptions(preset="subs", min_workers=1))
    check("fuse has 5 fields", all(k in out for k in judge_mod.FUSION_FIELDS))
    check("fuse sources populated", len(out["sources"]) == 4)
    check("fuse preset echoed", out["preset"] == "subs")
    check("fuse latency set", isinstance(out["total_latency"], (int, float)))


def test_cli_main_json() -> None:
    env = {
        "consensus": "C",
        "contradictions": ["d"],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }
    buf = io.StringIO()
    with (
        patch.object(
            panel_mod,
            "_cworker_worker",
            lambda m, t, to: {"source": m, "lane": "subscription", "success": True, "output": "o"},
        ),
        patch("cheap_llm.cheap_complete", _fake_cheap_complete(env)),
        patch.object(sys, "argv", ["fusion-local", "Q?", "--json", "--min-workers", "1"]),
        patch.object(sys, "stdout", buf),
    ):
        rc = fcli.main()
    parsed = json.loads(buf.getvalue())
    check("main --json exit 0", rc == 0, str(rc))
    check("main --json envelope", parsed["consensus"] == "C")


def test_cli_main_readable() -> None:
    env = {
        "consensus": "we agree",
        "contradictions": ["split"],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }
    buf = io.StringIO()
    with (
        patch.object(
            panel_mod,
            "_cworker_worker",
            lambda m, t, to: {"source": m, "lane": "subscription", "success": True, "output": "o"},
        ),
        patch("cheap_llm.cheap_complete", _fake_cheap_complete(env)),
        patch.object(sys, "argv", ["fusion-local", "Q?", "--min-workers", "1"]),
        patch.object(sys, "stdout", buf),
    ):
        rc = fcli.main()
    out = buf.getvalue()
    check("readable exit 0", rc == 0)
    check("readable has Consensus", "## Consensus" in out and "we agree" in out)
    check("readable has Meta", "## Meta" in out)


def test_cli_empty_prompt_errors() -> None:
    # argparse should error on empty prompt via our explicit check (parser.error).
    rc = -1
    try:
        with patch.object(sys, "argv", ["fusion-local", ""]):
            fcli.main()
    except SystemExit as exc:
        rc = exc.code
    check("empty prompt → non-zero exit", rc != 0 and rc is not None, str(rc))


TESTS = [
    ("panel_payg_uses_lane2_only", test_panel_payg_uses_lane2_only),
    ("panel_subs_falls_back_to_payg", test_panel_subs_falls_back_to_payg),
    ("panel_summarize", test_panel_summarize),
    ("cworker_router_unavailable", test_cworker_router_unavailable),
    ("judge_parses_5field", test_judge_parses_5field),
    ("judge_graceful_on_invalid_json", test_judge_graceful_on_invalid_json),
    ("judge_coerces_string_to_list", test_judge_coerces_string_to_list),
    ("judge_empty_panel", test_judge_empty_panel),
    ("fuse_integrates", test_fuse_integrates),
    ("cli_main_json", test_cli_main_json),
    ("cli_main_readable", test_cli_main_readable),
    ("cli_empty_prompt_errors", test_cli_empty_prompt_errors),
]


def main() -> int:
    print(f"fusion package tests — {len(TESTS)} cases\n")
    for name, fn in TESTS:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            global FAIL
            FAIL += 1
            FAILURES.append(f"{name}: raised {type(exc).__name__}: {exc}")
        else:
            print(f"  [ok] {name}")
    print(f"\nPASS={PASS} FAIL={FAIL}")
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print(f"  - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
