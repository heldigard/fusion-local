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
from importlib.metadata import version
from unittest.mock import patch

import fusion.cli as fcli
import fusion.judge as judge_mod
import fusion.panel as panel_mod
from fusion import FuseOptions, fuse

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        message = f"{name}: {detail}" if detail else name
        raise AssertionError(message)


# === panel feature ==========================================================


def test_panel_payg_uses_lane2_only() -> None:
    calls: list[str] = []

    def fake_http(spec, _task, _timeout):
        calls.append(f"http:{spec[0]}")
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    def fake_cworker(mode, _task, _timeout):
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
    def fake_cworker(mode, _task, _timeout):
        ok = mode == "codex-spark"
        return {
            "source": mode,
            "lane": "subscription",
            "success": ok,
            "output": "o" if ok else None,
            "error": None if ok else "no quota",
        }

    http_called: list[str] = []

    def fake_http(spec, _task, _timeout):
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


def _fake_cheap_complete(
    envelope: dict,
    *,
    json_valid: bool = True,
    fields_ok: bool | None = None,
    text: str | None = None,
):
    payload = {
        "text": text if text is not None else json.dumps(envelope),
        "model": "deepseek/deepseek-v4-flash",
        "tier": "T2",
        "latency": 1.0,
        "cost": 0.0,
        "json_valid": json_valid,
        "fields_ok": json_valid if fields_ok is None else fields_ok,
        "attempts": [],
        "error": None if json_valid else "invalid",
    }
    # Signature mirrors cheap_complete(system, prompt, **kw); caller passes kwargs by name,
    # so params cannot be renamed to _* even though the mock ignores them.
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
    check("invalid preserves panel evidence", jd["panel_evidence"][0]["output"] == "y")


def test_judge_rejects_missing_schema_fields() -> None:
    env = {
        "consensus": "C",
        "contradictions": [],
    }
    with patch("cheap_llm.cheap_complete", _fake_cheap_complete(env)):
        jd = judge_mod.run_judge("task", [{"source": "x", "output": "y"}])
    check("missing fields → judge_valid False", jd["judge_valid"] is False)
    check("missing fields → panel evidence kept", jd["panel_evidence"][0]["output"] == "y")
    check("missing fields → schema error", "schema" in (jd.get("error") or ""))


def test_judge_accepts_empty_schema_arrays() -> None:
    env = {
        "consensus": "C",
        "contradictions": [],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }
    with patch("cheap_llm.cheap_complete", _fake_cheap_complete(env)):
        jd = judge_mod.run_judge("task", [{"source": "x", "output": "y"}])
    check("empty fusion arrays accepted", jd["judge_valid"] is True)
    check("empty contradictions preserved", jd["contradictions"] == [])


def test_judge_preserves_panel_when_all_tiers_fail() -> None:
    with patch("cheap_llm.cheap_complete", _fake_cheap_complete({}, json_valid=False, text="")):
        jd = judge_mod.run_judge(
            "task",
            [{"source": "x", "lane": "payg", "success": True, "output": "panel answer"}],
        )
    check("empty judge → useful consensus", "panel_evidence" in jd["consensus"])
    check("empty judge → evidence output", jd["panel_evidence"][0]["output"] == "panel answer")


def test_payg_model_ids_are_current_shape() -> None:
    deepseek = [spec for spec in panel_mod.PANEL_PAYG if spec[0].startswith("deepseek")]
    check("deepseek payg model present", len(deepseek) == 1, str(deepseek))
    check("deepseek reasoner stale id removed", deepseek[0][2] != "deepseek/deepseek-reasoner")
    check("deepseek v3.2 stale id removed", deepseek[0][2] != "deepseek/deepseek-v3.2")
    check("deepseek model is v4 pro", deepseek[0][2] == "deepseek/deepseek-v4-pro")
    qwen = [spec for spec in panel_mod.PANEL_PAYG if spec[0].startswith("qwen")]
    check("qwen payg model present", len(qwen) == 1, str(qwen))
    check("qwen model uses canonical openrouter id", qwen[0][2] == "qwen/qwen3.7-max")


def test_run_lane_isolates_runner_exception() -> None:
    def flaky_runner(worker, _task, _timeout):
        if worker == "bad":
            raise RuntimeError("boom")
        return {"source": worker, "lane": "subscription", "success": True, "output": "ok"}

    res = panel_mod._run_lane(["good", "bad"], flaky_runner, "task", 1)
    ok = [r for r in res if r.get("success")]
    failed = [r for r in res if not r.get("success")]
    check("run_lane keeps good worker", len(ok) == 1 and ok[0]["source"] == "good", str(res))
    check(
        "run_lane reports failed worker",
        len(failed) == 1 and failed[0]["source"] == "bad",
        str(res),
    )


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
            lambda m, _t, _to: {
                "source": m,
                "lane": "subscription",
                "success": True,
                "output": "o",
            },
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
            lambda m, _t, _to: {
                "source": m,
                "lane": "subscription",
                "success": True,
                "output": "o",
            },
        ),
        patch("cheap_llm.cheap_complete", _fake_cheap_complete(env)),
        patch.object(sys, "argv", ["fusion-local", "Q?", "--json", "--min-workers", "1"]),
        patch.object(sys, "stdout", buf),
    ):
        rc = fcli.main()
    parsed = json.loads(buf.getvalue())
    check("main --json exit 0", rc == 0, str(rc))
    check("main --json envelope", parsed["consensus"] == "C")


def test_cli_version_uses_distribution_name() -> None:
    check("cli version from fusion-local dist", fcli.__version__ == version("fusion-local"))


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
            lambda m, _t, _to: {
                "source": m,
                "lane": "subscription",
                "success": True,
                "output": "o",
            },
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
    ("judge_rejects_missing_schema_fields", test_judge_rejects_missing_schema_fields),
    ("judge_accepts_empty_schema_arrays", test_judge_accepts_empty_schema_arrays),
    ("judge_preserves_panel_when_all_tiers_fail", test_judge_preserves_panel_when_all_tiers_fail),
    ("payg_model_ids_are_current_shape", test_payg_model_ids_are_current_shape),
    ("run_lane_isolates_runner_exception", test_run_lane_isolates_runner_exception),
    ("judge_coerces_string_to_list", test_judge_coerces_string_to_list),
    ("judge_empty_panel", test_judge_empty_panel),
    ("fuse_integrates", test_fuse_integrates),
    ("cli_main_json", test_cli_main_json),
    ("cli_version_uses_distribution_name", test_cli_version_uses_distribution_name),
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
