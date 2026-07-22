"""panel lanes, profiles, exclusions, scrub/summarize."""

from __future__ import annotations

import io
import urllib.error
from email.message import Message
from typing import Any
from unittest.mock import patch

from _fusion_harness import check

import fusion.panel as panel_mod


def test_panel_payg_uses_lane2_only() -> None:
    calls: list[str] = []

    def fake_http(spec, _task, _timeout):
        calls.append(f"http:{spec[0]}")
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    def fake_cworker(mode, _task, _timeout):
        calls.append(f"cw:{mode}")
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    with (
        # Isolate from the host session so detect_current_model() does not skip a seat.
        patch.dict("os.environ", {}, clear=True),
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


def test_panel_subs_falls_back_to_payg_only_with_opt_in() -> None:
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
        # Isolate from the host session so detect_current_model() does not skip a seat.
        patch.dict("os.environ", {}, clear=True),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        panel_mod.run_panel("task", preset="subs", min_workers=2)
        check("subs default blocks lane2 fallback", http_called == [], str(http_called))
        panel_mod.run_panel(
            "task",
            preset="subs",
            min_workers=2,
            allow_payg_fallback=True,
        )
    check("subs opt-in runs lane2 fallback", len(http_called) == 2, str(http_called))


def test_panel_subs_includes_all_documented_subscription_families() -> None:
    all_workers = {worker for workers in panel_mod.SUBS_PROFILES.values() for worker in workers}
    check(
        "profiles cover every paid subscription family",
        {
            "codex-spark",
            "claude-sonnet",
            "agy36-flash",
            "kimic",
            "zai",
            "mimo",
            "grok",
        }
        <= all_workers,
        str(panel_mod.SUBS_PROFILES),
    )
    check(
        "balanced profile stays bounded",
        tuple(panel_mod.PANEL_SUBS) == panel_mod.SUBS_PROFILES["balanced"]
        and len(panel_mod.PANEL_SUBS) == 3,
        str(panel_mod.PANEL_SUBS),
    )
    check(
        "Grok coding seat maps to Grok Build",
        "x-ai/grok-build-0.1" in panel_mod.SUBS_WORKER_MODELS["grok"],
        str(panel_mod.SUBS_WORKER_MODELS),
    )
    check(
        "named subscription profiles exclude metered workers",
        not (all_workers & panel_mod.CREDIT_ONLY_WORKERS),
        str(panel_mod.SUBS_PROFILES),
    )


def test_panel_subscription_profiles_select_task_specific_hands() -> None:
    calls: list[str] = []

    def fake_cworker(mode, _task, _timeout):
        calls.append(mode)
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
    ):
        panel_mod.run_panel("task", preset="subs", min_workers=1, subs_profile="coding")
    check(
        "coding profile dispatches only coding hands",
        set(calls) == set(panel_mod.SUBS_PROFILES["coding"]),
        str(calls),
    )


def test_panel_subscription_worker_override_precedes_profile() -> None:
    calls: list[str] = []

    def fake_cworker(mode, _task, _timeout):
        calls.append(mode)
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    with (
        patch.dict("os.environ", {"FUSION_PANEL_SUBS": "mini,mimo"}, clear=True),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
    ):
        panel_mod.run_panel("task", preset="subs", min_workers=1, subs_profile="reasoning")
    check("explicit worker override wins", calls == ["mini", "mimo"], str(calls))


def test_panel_explicit_profile_precedes_environment_default() -> None:
    calls: list[str] = []

    def fake_cworker(mode, _task, _timeout):
        calls.append(mode)
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    with (
        patch.dict("os.environ", {"FUSION_SUBS_PROFILE": "fast"}, clear=True),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
    ):
        panel_mod.run_panel("task", preset="subs", min_workers=1, subs_profile="coding")
    check(
        "explicit profile wins over environment default",
        set(calls) == set(panel_mod.SUBS_PROFILES["coding"]),
        str(calls),
    )


def test_panel_payg_ignores_invalid_subscription_profile_environment() -> None:
    calls: list[str] = []

    def fake_http(spec, _task, _timeout):
        calls.append(spec[0])
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with (
        patch.dict("os.environ", {"FUSION_SUBS_PROFILE": "invalid"}, clear=True),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        panel_mod.run_panel("task", preset="payg")
    check("PAYG ignores unrelated subscription env", len(calls) == len(panel_mod.PANEL_PAYG))


def test_panel_custom_workers_ignore_invalid_profile_environment() -> None:
    calls: list[str] = []

    def fake_cworker(mode, _task, _timeout):
        calls.append(mode)
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    with (
        patch.dict(
            "os.environ",
            {"FUSION_PANEL_SUBS": "kimic,zai", "FUSION_SUBS_PROFILE": "invalid"},
            clear=True,
        ),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
    ):
        panel_mod.run_panel("task", preset="subs", min_workers=1)
    check("custom worker list ignores profile env", calls == ["kimic", "zai"], str(calls))


def test_panel_rejects_credit_only_worker_in_subscription_lane() -> None:
    calls: list[str] = []

    def recorder(*_args, **_kwargs):
        calls.append("dispatch")
        return []

    with (
        patch.dict("os.environ", {"FUSION_PANEL_SUBS": "claude-fable"}, clear=True),
        patch.object(panel_mod, "_run_lane", recorder),
    ):
        raised = False
        try:
            panel_mod.run_panel("task", preset="subs")
        except ValueError as exc:
            raised = "credit-only worker" in str(exc) and "--preset ultra" in str(exc)
    check("credit-only Fable is rejected from lane 1", raised)
    check("credit-only rejection occurs before dispatch", calls == [], str(calls))


def test_panel_cheap_uses_low_cost_models() -> None:
    calls: list[str] = []

    def fake_http(spec, _task, _timeout):
        calls.append(spec[2])
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with (
        # Isolate from the host session so detect_current_model() does not skip a seat.
        patch.dict("os.environ", {}, clear=True),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        res = panel_mod.run_panel("task", preset="cheap")
    ok = [r for r in res if r["success"]]
    check("cheap preset calls all cheap workers", len(ok) == len(panel_mod.PANEL_CHEAP), str(res))
    check("cheap includes deepseek flash", "deepseek-ai/DeepSeek-V4-Flash" in calls, str(calls))
    check("cheap includes minimax m3", "minimax/minimax-m3" in calls, str(calls))
    check("cheap has two nonredundant seats", len(calls) == 2, str(calls))


def test_panel_ultra_uses_verified_frontier_models() -> None:
    calls: list[str] = []

    def fake_http(spec, _task, _timeout):
        calls.append(spec[2])
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with (
        # Isolate from the host session: under CLAUDECODE the panel now reads
        # the real settings.json controller and would rightly skip its seat.
        patch.dict("os.environ", {}, clear=True),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        res = panel_mod.run_panel("task", preset="ultra")
    ok = [r for r in res if r["success"]]
    check("ultra preset calls all ultra workers", len(ok) == len(panel_mod.PANEL_ULTRA), str(res))
    check("ultra includes fable", "anthropic/claude-fable-5" in calls, str(calls))
    check("ultra includes gpt 5.6 sol pro", "openai/gpt-5.6-sol-pro" in calls, str(calls))
    check("ultra excludes legacy gpt-5.5-pro", "openai/gpt-5.5-pro" not in calls, str(calls))
    check("ultra includes grok 4.5", "x-ai/grok-4.5" in calls, str(calls))
    check("ultra has three nonredundant families", len(calls) == 3, str(calls))


def test_panel_intelligence_uses_frontier_accessible_no_premium() -> None:
    calls: list[str] = []

    def fake_http(spec, _task, _timeout):
        calls.append(spec[2])
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        res = panel_mod.run_panel("task", preset="intelligence")
    ok = [r for r in res if r["success"]]
    check(
        "intelligence calls all intelligence workers",
        len(ok) == len(panel_mod.PANEL_INTELLIGENCE),
        str(res),
    )
    check("intelligence includes grok 4.5", "x-ai/grok-4.5" in calls, str(calls))
    check("intelligence includes gpt 5.6 terra", "openai/gpt-5.6-terra" in calls, str(calls))
    check("intelligence includes GLM 5.2", "z-ai/glm-5.2" in calls, str(calls))
    check("intelligence has three nonredundant families", len(calls) == 3, str(calls))
    # Intelligence deliberately excludes premium seats ultra reserves.
    check("intelligence excludes fable 5", "anthropic/claude-fable-5" not in calls, str(calls))
    check(
        "intelligence excludes gpt 5.6 sol pro", "openai/gpt-5.6-sol-pro" not in calls, str(calls)
    )


def test_panel_mixed_always_runs_both_lanes() -> None:
    calls: list[str] = []

    def fake_cworker(mode, _task, _timeout):
        calls.append(f"subs:{mode}")
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    def fake_http(spec, _task, _timeout):
        calls.append(f"payg:{spec[0]}")
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with (
        # Isolate from the host session so detect_current_model() does not skip a seat.
        patch.dict("os.environ", {}, clear=True),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        res = panel_mod.run_panel("task", preset="mixed", min_workers=1)
    check(
        "mixed runs all subscription workers",
        len([c for c in calls if c.startswith("subs")]) == len(panel_mod.PANEL_SUBS),
    )
    check("mixed runs default payg panel", len([c for c in calls if c.startswith("payg")]) == 2)
    check(
        "mixed returns every configured success",
        len([r for r in res if r["success"]])
        == len(panel_mod.PANEL_SUBS) + len(panel_mod.PANEL_PAYG),
        str(res),
    )

    calls.clear()
    with (
        # Isolate from the host session so detect_current_model() does not skip a seat.
        patch.dict("os.environ", {}, clear=True),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        res = panel_mod.run_panel(
            "task",
            preset="mixed",
            min_workers=1,
            current_model="deepseek/deepseek-v4-pro",
        )
    check("mixed excludes current payg model", "payg:deepseek-v4-pro" not in calls, str(calls))
    check("mixed reports current model skip", any(item.get("skipped") for item in res), str(res))


def test_panel_invalid_inputs_block_dispatch() -> None:
    calls: list[str] = []
    invalid_bool: Any = 1

    def recorder(*_args, **_kwargs):
        calls.append("dispatch")
        return []

    cases = [
        ("empty task", lambda: panel_mod.run_panel("", preset="subs")),
        ("unknown preset", lambda: panel_mod.run_panel("task", preset="unknown")),
        ("zero timeout", lambda: panel_mod.run_panel("task", timeout=0)),
        ("bool timeout", lambda: panel_mod.run_panel("task", timeout=True)),
        ("zero min workers", lambda: panel_mod.run_panel("task", min_workers=0)),
        ("blank model", lambda: panel_mod.run_panel("task", current_model=" ")),
        (
            "non-boolean PAYG fallback",
            lambda: panel_mod.run_panel("task", allow_payg_fallback=invalid_bool),
        ),
    ]
    with patch.object(panel_mod, "_run_lane", recorder):
        for name, invoke in cases:
            raised = False
            try:
                invoke()
            except ValueError:
                raised = True
            check(f"panel rejects {name}", raised)
    check("invalid panel input makes zero dispatch", calls == [], str(calls))


def test_panel_excludes_current_payg_model() -> None:
    calls: list[str] = []

    def fake_http(spec, _task, _timeout):
        calls.append(spec[2])
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with patch.object(panel_mod, "_http_worker", fake_http):
        res = panel_mod.run_panel(
            "task",
            preset="cheap",
            current_model="deepseek/deepseek-v4-flash",
        )
    check("current payg model not called", "deepseek-ai/DeepSeek-V4-Flash" not in calls, str(calls))
    skipped = [r for r in res if r.get("skipped")]
    check(
        "current payg model reported skipped",
        bool(skipped) and skipped[0]["source"] == "deepseek-v4-flash-di",
    )


def test_panel_excludes_current_subscription_model() -> None:
    calls: list[str] = []

    def fake_cworker(mode, _task, _timeout):
        calls.append(mode)
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    with (
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
        patch.object(panel_mod, "_http_worker", lambda *_args: {"success": False}),
    ):
        res = panel_mod.run_panel(
            "task",
            preset="subs",
            min_workers=1,
            current_model="moonshotai/kimi-k3",
        )
    check("current subscription worker not called", "kimic" not in calls, str(calls))
    check(
        "other subscription workers still called",
        "claude-sonnet" in calls and "zai" in calls,
        str(calls),
    )
    check("current subscription skip reported", any(r.get("skipped") for r in res), str(res))


def test_panel_excludes_current_grok_seat() -> None:
    calls: list[str] = []

    def fake_cworker(mode, _task, _timeout):
        calls.append(mode)
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    with (
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
        patch.object(panel_mod, "_http_worker", lambda *_args: {"success": False}),
    ):
        res = panel_mod.run_panel(
            "task",
            preset="subs",
            min_workers=1,
            current_model="x-ai/grok-build-0.1",
            subs_profile="coding",
        )
    check("current grok worker not called", "grok" not in calls, str(calls))
    check(
        "other subscription workers still called",
        "codex-spark" in calls and "claude-sonnet" in calls,
        str(calls),
    )
    skipped = [r for r in res if r.get("skipped")]
    check(
        "grok skip reported",
        bool(skipped) and skipped[0]["source"] == "grok",
        str(res),
    )


def test_panel_summarize() -> None:
    pr = [
        {"source": "a", "lane": "subscription", "output": "alpha"},
        {"source": "b", "lane": "payg", "success": False, "error": "x"},
    ]
    s = panel_mod.summarize(pr)
    check("summarize includes ok source", "a" in s and "alpha" in s)
    check("summarize excludes failed", "error" not in s.lower())


def test_panel_public_errors_hide_untrusted_details() -> None:
    marker = "SECRET_MARKER"
    with (
        patch.object(panel_mod.config, "ROUTER", panel_mod.Path(__file__)),
        patch.object(panel_mod.subprocess, "run", side_effect=RuntimeError(marker)),
    ):
        router = panel_mod._cworker_worker("codex-spark", "task", 5)
    check("router error hides exception detail", marker not in router["error"], router["error"])

    payg_spec = panel_mod.PANEL_PAYG[0]
    http_error = urllib.error.HTTPError(
        payg_spec[1],
        429,
        "rate limited",
        hdrs=Message(),
        fp=io.BytesIO(marker.encode()),
    )
    with (
        patch.dict("os.environ", {payg_spec[3]: "test-key"}),
        patch.object(panel_mod.urllib.request, "urlopen", side_effect=http_error),
    ):
        payg = panel_mod._http_worker(payg_spec, "task", 5)
    check("HTTP error reports status", "429" in payg["error"], payg["error"])
    check("HTTP error hides body", marker not in payg["error"], payg["error"])
    check("HTTP error is bounded", len(payg["error"]) <= 300, payg["error"])


def test_panel_scrubs_task_before_fanout() -> None:
    seen: list[str] = []

    def fake_http(spec, task, _timeout):
        seen.append(task)
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with (
        patch("cheap_llm.scrub_secrets", lambda _t: "SCRUBBED"),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        panel_mod.run_panel("secret sk-abc", preset="payg")
    check(
        "panel task scrubbed",
        bool(seen) and all(t == "SCRUBBED" for t in seen),
        str(seen),
    )


def test_direct_panel_scrub_failure_is_fail_closed() -> None:
    seen: list[str] = []

    def fake_http(spec, task, _timeout):
        seen.append(task)
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    error: BaseException | None = None
    with (
        patch("cheap_llm.scrub_secrets", side_effect=RuntimeError("scrub down")),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        try:
            panel_mod.run_panel("original task", preset="payg")
        except BaseException as exc:
            error = exc
    check("direct panel scrub failure raises safe boundary error", isinstance(error, RuntimeError))
    check("direct panel scrub failure dispatches nothing", seen == [], str(seen))


def test_panel_subs_env_override() -> None:
    modes: list[str] = []

    def fake_cworker(mode, _task, _timeout):
        modes.append(mode)
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    with (
        patch.dict("os.environ", {"FUSION_PANEL_SUBS": "modeA,modeB"}),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
    ):
        panel_mod.run_panel("task", preset="subs", min_workers=1)
    check("env override selects custom lane-1", sorted(modes) == ["modeA", "modeB"], str(modes))


def test_panel_subs_env_empty_disables_lane1() -> None:
    cworker_calls: list[str] = []
    http_calls: list[str] = []

    def fake_cworker(mode, _task, _timeout):
        cworker_calls.append(mode)
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    def fake_http(spec, _task, _timeout):
        http_calls.append(spec[0])
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with (
        patch.dict("os.environ", {"FUSION_PANEL_SUBS": ""}),
        patch.object(panel_mod, "_cworker_worker", fake_cworker),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        panel_mod.run_panel(
            "task",
            preset="subs",
            min_workers=2,
            allow_payg_fallback=True,
        )
    check("empty override skips lane-1", cworker_calls == [], str(cworker_calls))
    check("empty override uses explicitly authorized lane-2", len(http_calls) == 2, str(http_calls))


TESTS = [
    ("test_panel_payg_uses_lane2_only", test_panel_payg_uses_lane2_only),
    (
        "test_panel_subs_falls_back_to_payg_only_with_opt_in",
        test_panel_subs_falls_back_to_payg_only_with_opt_in,
    ),
    (
        "test_panel_subs_includes_all_documented_subscription_families",
        test_panel_subs_includes_all_documented_subscription_families,
    ),
    (
        "test_panel_subscription_profiles_select_task_specific_hands",
        test_panel_subscription_profiles_select_task_specific_hands,
    ),
    (
        "test_panel_subscription_worker_override_precedes_profile",
        test_panel_subscription_worker_override_precedes_profile,
    ),
    (
        "test_panel_explicit_profile_precedes_environment_default",
        test_panel_explicit_profile_precedes_environment_default,
    ),
    (
        "test_panel_payg_ignores_invalid_subscription_profile_environment",
        test_panel_payg_ignores_invalid_subscription_profile_environment,
    ),
    (
        "test_panel_custom_workers_ignore_invalid_profile_environment",
        test_panel_custom_workers_ignore_invalid_profile_environment,
    ),
    (
        "test_panel_rejects_credit_only_worker_in_subscription_lane",
        test_panel_rejects_credit_only_worker_in_subscription_lane,
    ),
    ("test_panel_cheap_uses_low_cost_models", test_panel_cheap_uses_low_cost_models),
    (
        "test_panel_ultra_uses_verified_frontier_models",
        test_panel_ultra_uses_verified_frontier_models,
    ),
    ("test_panel_mixed_always_runs_both_lanes", test_panel_mixed_always_runs_both_lanes),
    ("test_panel_invalid_inputs_block_dispatch", test_panel_invalid_inputs_block_dispatch),
    ("test_panel_excludes_current_payg_model", test_panel_excludes_current_payg_model),
    (
        "test_panel_excludes_current_subscription_model",
        test_panel_excludes_current_subscription_model,
    ),
    ("test_panel_excludes_current_grok_seat", test_panel_excludes_current_grok_seat),
    ("test_panel_summarize", test_panel_summarize),
    (
        "test_panel_public_errors_hide_untrusted_details",
        test_panel_public_errors_hide_untrusted_details,
    ),
    ("test_panel_scrubs_task_before_fanout", test_panel_scrubs_task_before_fanout),
    (
        "test_direct_panel_scrub_failure_is_fail_closed",
        test_direct_panel_scrub_failure_is_fail_closed,
    ),
    ("test_panel_subs_env_override", test_panel_subs_env_override),
    ("test_panel_subs_env_empty_disables_lane1", test_panel_subs_env_empty_disables_lane1),
    # dormant in the pre-split gate; kept defined + pytest-collected:
    # test_panel_intelligence_uses_frontier_accessible_no_premium
]
