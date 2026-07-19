"""CLI entrypoints, version, capabilities, openrouter routing."""

from __future__ import annotations

import io
import json
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from unittest.mock import patch

from _fusion_harness import _fake_cheap_complete, check

import fusion
import fusion._version as version_mod
import fusion.cli as fcli
import fusion.judge as judge_mod
import fusion.panel as panel_mod


def test_payg_model_ids_are_current_shape() -> None:
    deepseek = [spec for spec in panel_mod.PANEL_PAYG if spec[0].startswith("deepseek")]
    check("deepseek payg model present", len(deepseek) == 1, str(deepseek))
    check("deepseek reasoner stale id removed", deepseek[0][2] != "deepseek/deepseek-reasoner")
    check("deepseek v3.2 stale id removed", deepseek[0][2] != "deepseek/deepseek-v3.2")
    check("deepseek model is v4 pro", deepseek[0][2] == "deepseek-v4-pro")
    check("deepseek uses first-party api", "api.deepseek.com" in deepseek[0][1], str(deepseek[0]))
    check(
        "deepseek uses DEEPSEEK_API_KEY",
        deepseek[0][3] == panel_mod.DEEPSEEK_KEY_ENV,
        str(deepseek[0]),
    )
    qwen = [spec for spec in panel_mod.PANEL_PAYG if spec[0].startswith("qwen")]
    check("qwen payg model present", len(qwen) == 1, str(qwen))
    canonical = [spec[0].removesuffix("-di") for spec in panel_mod.PANEL_PAYG]
    check(
        "payg quorum seats are unique models",
        len(canonical) == len(set(canonical)),
        str(canonical),
    )
    check("qwen model uses canonical ZenMux id", qwen[0][2] == "qwen/qwen3.7-max")
    check("qwen uses lower-cost ZenMux route", qwen[0][3] == panel_mod.ZENMUX_KEY_ENV)
    cheap_ids = {spec[2] for spec in panel_mod.PANEL_CHEAP}
    check("cheap deepseek is flash", "deepseek-ai/DeepSeek-V4-Flash" in cheap_ids, str(cheap_ids))
    check("cheap minimax is m3", "minimax/minimax-m3" in cheap_ids, str(cheap_ids))
    check("cheap drops dominated Qwen Plus", "qwen/qwen3.7-plus" not in cheap_ids, str(cheap_ids))
    check(
        "cheap drops general-purpose MiMo seat",
        "xiaomi/mimo-v2.5-pro" not in cheap_ids,
        str(cheap_ids),
    )
    ultra_ids = {spec[2] for spec in panel_mod.PANEL_ULTRA}
    check("ultra fable 5 present", "anthropic/claude-fable-5" in ultra_ids, str(ultra_ids))
    check(
        "ultra uses verified gpt 5.6 sol pro", "openai/gpt-5.6-sol-pro" in ultra_ids, str(ultra_ids)
    )
    check("ultra drops legacy gpt 5.5 pro", "openai/gpt-5.5-pro" not in ultra_ids, str(ultra_ids))
    check("ultra includes grok 4.5", "x-ai/grok-4.5" in ultra_ids, str(ultra_ids))
    check(
        "ultra excludes dominated opus sibling",
        "anthropic/claude-opus-4.8" not in ultra_ids,
        str(ultra_ids),
    )
    check(
        "ultra avoids unverified gemini 3.5 pro id",
        "google/gemini-3.5-pro" not in ultra_ids,
        str(ultra_ids),
    )
    intel_ids = {spec[2] for spec in panel_mod.PANEL_INTELLIGENCE}
    check("intelligence includes grok 4.5", "x-ai/grok-4.5" in intel_ids, str(intel_ids))
    check(
        "intelligence includes gpt 5.6 terra", "openai/gpt-5.6-terra" in intel_ids, str(intel_ids)
    )
    check(
        "intelligence includes GLM 5.2",
        "z-ai/glm-5.2" in intel_ids,
        str(intel_ids),
    )
    check(
        "intelligence excludes premium fable 5",
        "anthropic/claude-fable-5" not in intel_ids,
        str(intel_ids),
    )
    check(
        "intelligence excludes premium gpt 5.6 sol pro",
        "openai/gpt-5.6-sol-pro" not in intel_ids,
        str(intel_ids),
    )
    check(
        "intelligence registered in presets",
        "intelligence" in panel_mod.PANEL_PRESETS,
        str(panel_mod.PANEL_PRESETS),
    )


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
            "_http_worker",
            lambda spec, _t, _to: {
                "source": spec[0],
                "lane": "payg",
                "success": True,
                "output": "o",
            },
        ),
        patch("cheap_llm.cheap_complete", _fake_cheap_complete(env)),
        patch.object(
            sys,
            "argv",
            [
                "fusion-local",
                "Q?",
                "--preset",
                "cheap",
                "--current-model",
                "qwen/qwen3.7-plus",
                "--json",
            ],
        ),
        patch.object(sys, "stdout", buf),
    ):
        rc = fcli.main()
    parsed = json.loads(buf.getvalue())
    check("main --json exit 0", rc == 0, str(rc))
    check("main --json envelope", parsed["consensus"] == "C")
    check("main --json current model", parsed["current_model"] == "qwen/qwen3.7-plus")


def test_cli_cloud_judge_flag() -> None:
    args = fcli._build_parser().parse_args(["Q?", "--cloud-judge"])
    check("CLI exposes explicit cloud-only judge", args.cloud_judge is True)


def test_cli_version_uses_distribution_name() -> None:
    expected = distribution_version("fusion-local")
    check("package version from fusion-local dist", fusion.__version__ == expected)
    check("cli version shares package version", fcli.__version__ == fusion.__version__)


def test_version_source_fallback_is_honest() -> None:
    with patch.object(version_mod, "version", side_effect=PackageNotFoundError):
        resolved = version_mod.resolve_version()
    check("source fallback is unknown", resolved == "0+unknown", resolved)


def test_cli_capabilities_contract() -> None:
    buf = io.StringIO()
    with (
        patch.object(sys, "argv", ["fusion-local", "--capabilities"]),
        patch.object(sys, "stdout", buf),
    ):
        rc = fcli.main()
    payload = json.loads(buf.getvalue())
    by_name = {item["name"]: item for item in payload["capabilities"]}
    check("capabilities exit 0", rc == 0, str(rc))
    check("capabilities schema", payload["schema_version"] == 1, str(payload))
    check("capabilities canonical version", payload["version"] == fusion.__version__)
    check("fuse structured", by_name["fuse"]["structured_json"] is True, str(by_name["fuse"]))
    check(
        "structured flag semantics explicit",
        "not describe the default" in payload["field_semantics"]["structured_json"],
        str(payload["field_semantics"]),
    )
    check("fuse supports JSON", by_name["fuse"]["supports_json_output"] is True)
    check("fuse default is text", by_name["fuse"]["default_output_format"] == "text")
    check(
        "capabilities default is JSON",
        by_name["capabilities"]["default_output_format"] == "json",
    )
    check("hosted default is text", by_name["openrouter"]["default_output_format"] == "text")
    for name in ("fuse", "capabilities", "openrouter"):
        entry = by_name[name]
        check(f"{name} invocation discoverable", bool(entry["invocation"]["cli"]), str(entry))
        check(f"{name} exits discoverable", bool(entry["exit_codes"]), str(entry))
        check(f"{name} recovery discoverable", bool(entry["recovery"]), str(entry))
    check("fuse read-only", by_name["fuse"]["read_only"] is True, str(by_name["fuse"]))
    check("capabilities presets DRY", tuple(by_name["fuse"]["presets"]) == panel_mod.PANEL_PRESETS)
    check(
        "local JSON contract named",
        by_name["fuse"]["output_contracts"]["json"] == "fusion-envelope-v1",
    )
    check(
        "hosted raw JSON contract named",
        by_name["openrouter"]["output_contracts"]["json"] == "openrouter-chat-completion-v1",
    )
    check(
        "health exposes cheap_llm",
        payload["health"]["cheap_llm_min_version"] == judge_mod.CHEAP_LLM_MIN_VERSION,
    )


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


def test_cli_rejects_invalid_options_before_preflight() -> None:
    calls: list[str] = []

    def recorder():
        calls.append("preflight")
        return {"ok": True, "version": "test", "error": None}

    argv_cases = [
        ["fusion-local", "Q", "--panel-timeout", "0"],
        ["fusion-local", "Q", "--judge-timeout", "-1"],
        ["fusion-local", "Q", "--min-workers", "0"],
        ["fusion-local", "Q", "--cloud-model", ""],
        ["fusion-local", "Q", "--current-model", " "],
    ]
    with patch.object(fcli, "preflight", recorder):
        for argv in argv_cases:
            code = None
            try:
                with patch.object(sys, "argv", argv):
                    fcli.main()
            except SystemExit as exc:
                code = exc.code
            check("CLI invalid option exits 2", code == 2, str((argv, code)))
    check("CLI invalid options make zero preflight", calls == [], str(calls))


def test_openrouter_help_version_and_capabilities_routing() -> None:
    for flag in ("--help", "--version"):
        code = None
        try:
            with patch.object(sys, "argv", ["fusion", "--openrouter", flag]):
                fcli.main()
        except SystemExit as exc:
            code = exc.code
        check(f"hosted {flag} exits 0", code == 0, str(code))

    code = None
    try:
        with patch.object(sys, "argv", ["fusion", "--openrouter", "--capabilities"]):
            fcli.main()
    except SystemExit as exc:
        code = exc.code
    check("hosted capabilities is invalid usage", code == 2, str(code))


# === hardening: preflight / scrub / env override / health ==================


def test_capabilities_health_live() -> None:
    import fusion.capabilities as caps_mod

    payload = caps_mod.capabilities_payload()
    health = payload["health"]
    check(
        "health min version DRY with judge",
        health["cheap_llm_min_version"] == judge_mod.CHEAP_LLM_MIN_VERSION,
        str(health),
    )
    check("health names panel subs env", health["panel_subs_env"] == "FUSION_PANEL_SUBS")
    live = health["live"]
    check("live cheap_llm probe ok", live["cheap_llm_ok"] is True, str(live))
    check("live reports cheap_llm version", bool(live["cheap_llm_version"]), str(live))
    check("live router probe is bool", isinstance(live["router_available"], bool))
    check("live key probe is bool", isinstance(live["openrouter_key_present"], bool))
    check("live deepseek key probe is bool", isinstance(live["deepseek_key_present"], bool))
    check("live deepinfra key probe is bool", isinstance(live["deepinfra_key_present"], bool))


def test_cli_json_exit_reflects_judge_validity() -> None:
    buf = io.StringIO()
    with (
        patch.object(
            panel_mod,
            "_http_worker",
            lambda spec, _t, _to: {
                "source": spec[0],
                "lane": "payg",
                "success": True,
                "output": "o",
            },
        ),
        patch("cheap_llm.cheap_complete", _fake_cheap_complete({}, json_valid=False, text="raw")),
        patch.object(sys, "argv", ["fusion-local", "Q?", "--preset", "cheap", "--json"]),
        patch.object(sys, "stdout", buf),
    ):
        rc = fcli.main()
    parsed = json.loads(buf.getvalue())
    check("json exit 2 on invalid judge", rc == 2, str(rc))
    check("json envelope still parseable", parsed["judge_valid"] is False)


def test_cli_json_degrades_on_judge_exception() -> None:
    def fail_transport(*_args, **_kwargs):
        raise TimeoutError("transport down")

    buf = io.StringIO()
    with (
        patch.object(
            panel_mod,
            "_http_worker",
            lambda spec, _t, _to: {
                "source": spec[0],
                "lane": "payg",
                "success": True,
                "output": "panel signal",
            },
        ),
        patch("cheap_llm.cheap_complete", fail_transport),
        patch.object(sys, "argv", ["fusion-local", "Q?", "--preset", "cheap", "--json"]),
        patch.object(sys, "stdout", buf),
    ):
        rc = fcli.main()
    parsed = json.loads(buf.getvalue())
    check("judge exception CLI exits 2", rc == 2, str(rc))
    check("judge exception CLI stays JSON", parsed["judge_valid"] is False, buf.getvalue())
    check(
        "judge exception CLI keeps evidence",
        len(parsed["panel_evidence"]) == len(panel_mod.PANEL_CHEAP),
        str(parsed),
    )
    check("judge exception CLI has no traceback", "Traceback" not in buf.getvalue())


TESTS = [
    ("test_payg_model_ids_are_current_shape", test_payg_model_ids_are_current_shape),
    ("test_cli_main_json", test_cli_main_json),
    ("test_cli_cloud_judge_flag", test_cli_cloud_judge_flag),
    ("test_cli_version_uses_distribution_name", test_cli_version_uses_distribution_name),
    ("test_version_source_fallback_is_honest", test_version_source_fallback_is_honest),
    ("test_cli_capabilities_contract", test_cli_capabilities_contract),
    ("test_cli_main_readable", test_cli_main_readable),
    ("test_cli_empty_prompt_errors", test_cli_empty_prompt_errors),
    (
        "test_cli_rejects_invalid_options_before_preflight",
        test_cli_rejects_invalid_options_before_preflight,
    ),
    (
        "test_openrouter_help_version_and_capabilities_routing",
        test_openrouter_help_version_and_capabilities_routing,
    ),
    ("test_capabilities_health_live", test_capabilities_health_live),
    ("test_cli_json_exit_reflects_judge_validity", test_cli_json_exit_reflects_judge_validity),
    ("test_cli_json_degrades_on_judge_exception", test_cli_json_degrades_on_judge_exception),
]
