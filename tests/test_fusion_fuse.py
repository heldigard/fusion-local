"""fuse integration, envelope, preflight, scrub, quorum."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from _fusion_harness import _fake_cheap_complete, check

import fusion.cli as fcli
import fusion.judge as judge_mod
import fusion.panel as panel_mod
from fusion import FuseOptions, fuse
from fusion.capabilities import FUSE_ENVELOPE_FIELDS


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
    check("fuse sources populated", len(out["sources"]) == len(panel_mod.PANEL_SUBS))
    check("fuse preset echoed", out["preset"] == "subs")
    check("fuse latency set", isinstance(out["total_latency"], (int, float)))


def test_fuse_derives_judge_spend_policy_from_explicit_authority() -> None:
    cloud_policies: list[bool] = []
    env = {
        "consensus": "C",
        "contradictions": [],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }

    def fake_judge(system, prompt, **kwargs):
        cloud_policies.append(kwargs["allow_cloud"])
        return _fake_cheap_complete(env)(system, prompt, **kwargs)

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
        patch("cheap_llm.cheap_complete", fake_judge),
    ):
        fuse("task", opts=FuseOptions(preset="subs", min_workers=1))
        fuse(
            "task",
            opts=FuseOptions(
                preset="subs",
                min_workers=1,
                allow_payg_fallback=True,
            ),
        )
        fuse("task", opts=FuseOptions(preset="cheap", min_workers=1))
    check(
        "subscription default blocks cloud while explicit authorities permit it",
        cloud_policies == [False, True, True],
        str(cloud_policies),
    )


def test_fuse_scales_judge_with_preset() -> None:
    judge_kwargs: list[dict[str, Any]] = []
    env = {
        "consensus": "C",
        "contradictions": [],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }

    def fake_judge(system, prompt, **kwargs):
        judge_kwargs.append(kwargs)
        return _fake_cheap_complete(env)(system, prompt, **kwargs)

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
        patch("cheap_llm.cheap_complete", fake_judge),
    ):
        fuse("task", opts=FuseOptions(preset="ultra", min_workers=1))
        fuse("task", opts=FuseOptions(preset="intelligence", min_workers=1))
        fuse("task", opts=FuseOptions(preset="cheap", min_workers=1))
    models = [kwargs["cloud_model"] for kwargs in judge_kwargs]
    check(
        "frontier presets judge with the strong cloud model",
        models
        == [
            judge_mod.STRONG_JUDGE_MODEL,
            judge_mod.STRONG_JUDGE_MODEL,
            judge_mod.DEFAULT_JUDGE_MODEL,
        ],
        str(models),
    )
    prefer_local = [kwargs["prefer_local"] for kwargs in judge_kwargs]
    check(
        "frontier presets skip the weak local judge; cheap keeps local-first",
        prefer_local == [False, False, True],
        str(prefer_local),
    )


def test_fuse_explicit_judge_options_win_over_preset_scaling() -> None:
    judge_kwargs: list[dict[str, Any]] = []
    env = {
        "consensus": "C",
        "contradictions": [],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }

    def fake_judge(system, prompt, **kwargs):
        judge_kwargs.append(kwargs)
        return _fake_cheap_complete(env)(system, prompt, **kwargs)

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
        patch("cheap_llm.cheap_complete", fake_judge),
    ):
        fuse(
            "task",
            opts=FuseOptions(
                preset="ultra",
                min_workers=1,
                cloud_model="acme/custom-judge",
                judge_prefer_local=True,
            ),
        )
    check(
        "explicit judge options override preset scaling",
        judge_kwargs[0]["cloud_model"] == "acme/custom-judge"
        and judge_kwargs[0]["prefer_local"] is True,
        str(judge_kwargs),
    )


def test_fuse_judge_timeout_default_covers_cold_local_plus_cloud() -> None:
    judge_kwargs: list[dict[str, Any]] = []
    env = {
        "consensus": "C",
        "contradictions": [],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }

    def fake_judge(system, prompt, **kwargs):
        judge_kwargs.append(kwargs)
        return _fake_cheap_complete(env)(system, prompt, **kwargs)

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
        patch("cheap_llm.cheap_complete", fake_judge),
    ):
        fuse("task", opts=FuseOptions(preset="cheap", min_workers=1))
    check(
        "judge timeout default covers cold T1 (~25s) plus T2 (~18s)",
        judge_kwargs[0]["timeout_total"] >= 43.0,
        str(judge_kwargs),
    )
    check(
        "CLI --judge-timeout default matches the FuseOptions default",
        fcli._build_parser().parse_args(["Q?"]).judge_timeout == FuseOptions().judge_timeout,
    )


def test_fuse_reports_custom_subscription_worker_list() -> None:
    with (
        patch.dict("os.environ", {"FUSION_PANEL_SUBS": "kimic,zai"}, clear=True),
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
    check("custom subscription list is observable", out["subs_profile"] == "custom", str(out))
    check("custom subscription sources are exact", len(out["sources"]) == 2, str(out["sources"]))


def test_fuse_preserves_metadata_on_judge_exception() -> None:
    def fail_transport(*_args, **_kwargs):
        raise TimeoutError("transport down")

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
    ):
        out = fuse("task", opts=FuseOptions(preset="cheap"))
    check("fuse judge exception invalid", out["judge_valid"] is False, str(out))
    check(
        "fuse judge exception sources",
        len(out["sources"]) == len(panel_mod.PANEL_CHEAP),
        str(out["sources"]),
    )
    check("fuse judge exception preset", out["preset"] == "cheap", str(out))
    check("fuse judge exception latency", isinstance(out["total_latency"], (int, float)))
    check(
        "fuse judge exception evidence",
        len(out["panel_evidence"]) == len(panel_mod.PANEL_CHEAP),
        str(out),
    )


def test_fuse_invalid_inputs_block_preflight() -> None:
    calls: list[str] = []

    def recorder():
        calls.append("preflight")
        return {"ok": True, "version": "test", "error": None}

    invalid_opts: Any = "bad"
    invalid_bool: Any = 1
    cases = [
        lambda: fuse(""),
        lambda: fuse("task", opts=invalid_opts),
        lambda: fuse("task", opts=FuseOptions(preset="unknown")),
        lambda: fuse("task", opts=FuseOptions(panel_timeout=0)),
        lambda: fuse("task", opts=FuseOptions(judge_timeout=True)),
        lambda: fuse("task", opts=FuseOptions(min_workers=0)),
        lambda: fuse("task", opts=FuseOptions(cloud_model=" ")),
        lambda: fuse("task", opts=FuseOptions(current_model=" ")),
        lambda: fuse("task", opts=FuseOptions(judge_prefer_local=invalid_bool)),
        lambda: fuse("task", opts=FuseOptions(allow_payg_fallback=invalid_bool)),
    ]
    with patch.object(fcli, "preflight", recorder):
        for invoke in cases:
            raised = False
            try:
                invoke()
            except ValueError:
                raised = True
            check("fuse rejects invalid input", raised)
    check("invalid fuse input makes zero preflight", calls == [], str(calls))


def test_fuse_echoes_current_model() -> None:
    env = {
        "consensus": "C",
        "contradictions": [],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }
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
    ):
        out = fuse(
            "task",
            opts=FuseOptions(
                preset="cheap",
                current_model="deepseek/deepseek-v4-flash",
            ),
        )
    check("fuse current model echoed", out["current_model"] == "deepseek/deepseek-v4-flash")
    check(
        "fuse source skip metadata",
        any(s.get("skipped") for s in out["sources"]),
        str(out["sources"]),
    )


def test_fuse_envelope_matches_declared_contract() -> None:
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
    envelope_keys = set(out)
    declared = set(FUSE_ENVELOPE_FIELDS)
    check(
        "no undeclared envelope keys leak",
        envelope_keys <= declared,
        str(envelope_keys - declared),
    )
    # error/panel_evidence/current_model are intentionally conditional; the rest
    # of the declared field set must always be present on a successful subs fuse().
    always_present = declared - {"error", "panel_evidence", "current_model"}
    check(
        "declared always-present fields emitted",
        always_present <= envelope_keys,
        str(always_present - envelope_keys),
    )
    check("total_known_cost emitted on success", "total_known_cost" in out, str(out))


def test_fuse_total_known_cost_present_on_nonnumeric_judge_cost() -> None:
    envelope = {
        "consensus": "C",
        "contradictions": [],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }
    # Defensive case: provider returns a valid 5-field envelope but a non-numeric
    # usage cost. total_known_cost is an always-present contract field, so it must
    # still be emitted (defaulting the judge share to 0), never omitted.
    payload = {
        "text": json.dumps(envelope),
        "model": "deepseek/deepseek-v4-flash",
        "tier": "T2",
        "latency": 1.0,
        "cost": "not-a-number",
        "json_valid": True,
        "fields_ok": True,
        "attempts": [],
        "error": None,
    }
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
        patch("cheap_llm.cheap_complete", lambda system, prompt, **kw: payload),
    ):
        out = fuse("task", opts=FuseOptions(preset="cheap"))
    check(
        "non-numeric judge cost still yields total_known_cost",
        "total_known_cost" in out,
        str(out),
    )
    value = out.get("total_known_cost")
    check(
        "total_known_cost numeric on non-numeric judge cost",
        isinstance(value, (int, float)) and not isinstance(value, bool),
        str(value),
    )


def test_fuse_preflight_blocks_panel_spend() -> None:
    calls: list[str] = []

    def recorder(mode, _task, _timeout):
        calls.append(mode)
        return {"source": mode, "lane": "subscription", "success": True, "output": "o"}

    gate = {"ok": False, "version": None, "error": "cheap_llm unavailable (test)"}
    with (
        patch.object(fcli, "preflight", lambda: gate),
        patch.object(panel_mod, "_cworker_worker", recorder),
        patch.object(panel_mod, "_http_worker", recorder),
    ):
        out = fuse("task", opts=FuseOptions(preset="subs"))
    check("preflight fail → no panel spend", calls == [], str(calls))
    check("preflight fail → judge invalid", out["judge_valid"] is False)
    check("preflight fail → actionable error", "cheap_llm" in out["error"], str(out))
    check("preflight fail → empty sources", out["sources"] == [])
    check("preflight fail → preset echoed", out["preset"] == "subs")


def test_fuse_degrades_before_dispatch_when_scrub_fails() -> None:
    calls: list[str] = []

    def fake_http(spec, _task, _timeout):
        calls.append(spec[0])
        return {"source": spec[0], "lane": "payg", "success": True, "output": "o"}

    with (
        patch("cheap_llm.scrub_secrets", side_effect=RuntimeError("SECRET_MARKER")),
        patch.object(panel_mod, "_http_worker", fake_http),
    ):
        out = fuse("task", opts=FuseOptions(preset="payg"))
    check("scrub failure makes zero provider calls", calls == [], str(calls))
    check("scrub failure is degraded", out["status"] == "degraded", str(out))
    check("scrub failure hides exception detail", "SECRET_MARKER" not in out["error"], out["error"])


def test_fuse_requires_final_panel_quorum() -> None:
    judge_calls: list[str] = []

    def fake_http(spec, _task, _timeout):
        success = spec[0] == "deepseek-v4-pro"
        return {
            "source": spec[0],
            "lane": "payg",
            "success": success,
            "output": "only one answer" if success else None,
            "error": None if success else "provider unavailable",
        }

    def fake_judge(*_args, **_kwargs):
        judge_calls.append("called")
        return {}

    with (
        patch.object(panel_mod, "_http_worker", fake_http),
        patch("cheap_llm.cheap_complete", fake_judge),
    ):
        out = fuse("task", opts=FuseOptions(preset="payg", min_workers=2))
    check("one-seat panel does not call judge", judge_calls == [], str(judge_calls))
    check("one-seat panel degrades", out["judge_valid"] is False, str(out))
    check(
        "quorum metadata is explicit and carries per-seat status",
        out["panel_quorum"]
        == {
            "required": 2,
            "successful": 1,
            "met": False,
            "seats": [
                {"source": "deepseek-v4-pro", "lane": "payg", "outcome": "responded"},
                {"source": "qwen3.7-max-zm", "lane": "payg", "outcome": "failed"},
            ],
        },
        str(out["panel_quorum"]),
    )


TESTS = [
    ("test_fuse_integrates", test_fuse_integrates),
    (
        "test_fuse_derives_judge_spend_policy_from_explicit_authority",
        test_fuse_derives_judge_spend_policy_from_explicit_authority,
    ),
    ("test_fuse_scales_judge_with_preset", test_fuse_scales_judge_with_preset),
    (
        "test_fuse_explicit_judge_options_win_over_preset_scaling",
        test_fuse_explicit_judge_options_win_over_preset_scaling,
    ),
    (
        "test_fuse_judge_timeout_default_covers_cold_local_plus_cloud",
        test_fuse_judge_timeout_default_covers_cold_local_plus_cloud,
    ),
    (
        "test_fuse_reports_custom_subscription_worker_list",
        test_fuse_reports_custom_subscription_worker_list,
    ),
    (
        "test_fuse_preserves_metadata_on_judge_exception",
        test_fuse_preserves_metadata_on_judge_exception,
    ),
    ("test_fuse_invalid_inputs_block_preflight", test_fuse_invalid_inputs_block_preflight),
    ("test_fuse_echoes_current_model", test_fuse_echoes_current_model),
    ("test_fuse_envelope_matches_declared_contract", test_fuse_envelope_matches_declared_contract),
    (
        "test_fuse_total_known_cost_present_on_nonnumeric_judge_cost",
        test_fuse_total_known_cost_present_on_nonnumeric_judge_cost,
    ),
    ("test_fuse_preflight_blocks_panel_spend", test_fuse_preflight_blocks_panel_spend),
    (
        "test_fuse_degrades_before_dispatch_when_scrub_fails",
        test_fuse_degrades_before_dispatch_when_scrub_fails,
    ),
    ("test_fuse_requires_final_panel_quorum", test_fuse_requires_final_panel_quorum),
]
