"""cworker/http_worker transport safety + usage guards."""

from __future__ import annotations

import io
import json
import subprocess
from unittest.mock import patch

from _fusion_harness import check

import fusion.panel as panel_mod


def test_cworker_router_unavailable() -> None:
    # When ROUTER is None (FUSION_ROUTER=""), _cworker_worker returns graceful error.
    with patch.object(panel_mod.config, "ROUTER", None):
        res = panel_mod._cworker_worker("codex-spark", "task", 5)
    check(
        "router None → graceful fail",
        res["success"] is False and "router" in res["error"],
        res["error"],
    )


def test_cworker_rejects_nonzero_exit_with_stdout() -> None:
    proc = subprocess.CompletedProcess(
        args=["router"],
        returncode=17,
        stdout="partial answer that must not become evidence",
        stderr="router failed\n" + ("x" * 400),
    )
    with (
        patch.object(panel_mod.config, "ROUTER", panel_mod.Path(__file__)),
        patch.object(panel_mod.subprocess, "run", return_value=proc),
    ):
        res = panel_mod._cworker_worker("codex-spark", "task", 5)
    check("nonzero router exit fails", res["success"] is False, str(res))
    check("nonzero router output discarded", "output" not in res, str(res))
    check("router error includes status", "status 17" in res["error"], res["error"])
    check("router error is bounded", len(res["error"]) <= 300, str(len(res["error"])))
    check("router error is single-line", "\n" not in res["error"], res["error"])
    check("router error excludes stdout", "partial answer" not in res["error"], res["error"])


def test_cworker_accepts_zero_exit_with_stdout() -> None:
    proc = subprocess.CompletedProcess(
        args=["router"], returncode=0, stdout="complete answer", stderr=""
    )
    with (
        patch.object(panel_mod.config, "ROUTER", panel_mod.Path(__file__)),
        patch.object(panel_mod.subprocess, "run", return_value=proc) as run_mock,
    ):
        res = panel_mod._cworker_worker("codex-spark", "task", 5)
    check("zero router exit succeeds", res["success"] is True, str(res))
    check("zero router output preserved", res["output"] == "complete answer", str(res))
    argv = run_mock.call_args.args[0]
    check("fusion router protocol requested", argv[-2:] == ["--protocol", "fusion-panel-v1"])


def test_cworker_rejects_oversized_stdout() -> None:
    proc = subprocess.CompletedProcess(
        args=["router"],
        returncode=0,
        stdout="x" * (panel_mod.MAX_EXTERNAL_RESPONSE_BYTES + 1),
        stderr="",
    )
    with (
        patch.object(panel_mod.config, "ROUTER", panel_mod.Path(__file__)),
        patch.object(panel_mod.subprocess, "run", return_value=proc),
    ):
        res = panel_mod._cworker_worker("codex-spark", "task", 5)
    check("oversized router output fails", res["success"] is False, str(res))
    check("oversized router output is discarded", "output" not in res, str(res))


def test_http_worker_rejects_non_string_content() -> None:
    response = {"choices": [{"message": {"content": [{"type": "text", "text": "x"}]}}]}
    payg_spec = panel_mod.PANEL_PAYG[0]
    with (
        patch.dict("os.environ", {payg_spec[3]: "test-key"}),
        patch.object(
            panel_mod.urllib.request,
            "urlopen",
            return_value=io.BytesIO(json.dumps(response).encode()),
        ),
    ):
        result = panel_mod._http_worker(payg_spec, "task", 5)
    check("non-string HTTP content fails", result["success"] is False, str(result))
    check("non-string HTTP content is malformed", result["error"] == "malformed response")


def test_safe_usage_allows_only_nonnegative_numeric_metrics() -> None:
    usage = panel_mod._safe_usage(
        {
            "prompt_tokens": 10,
            "completion_tokens": 5.0,
            "total_tokens": True,
            "cost": -1,
            "prompt": "must never escape",
        }
    )
    check(
        "usage retains safe token counters",
        usage == {"prompt_tokens": 10, "completion_tokens": 5.0},
        str(usage),
    )
    check("usage drops arbitrary provider fields", "prompt" not in usage, str(usage))


def test_http_worker_rejects_oversized_response() -> None:
    payg_spec = panel_mod.PANEL_PAYG[0]
    with (
        patch.dict("os.environ", {payg_spec[3]: "test-key"}),
        patch.object(panel_mod, "MAX_EXTERNAL_RESPONSE_BYTES", 10),
        patch.object(panel_mod.urllib.request, "urlopen", return_value=io.BytesIO(b"x" * 11)),
    ):
        result = panel_mod._http_worker(payg_spec, "task", 5)
    check("oversized PAYG response fails", result["success"] is False, str(result))
    check("oversized PAYG response is stable", result["error"] == "payg response too large")


def test_http_worker_rejects_invalid_utf8() -> None:
    raw = b'{"choices":[{"message":{"content":"\xff"}}]}'
    payg_spec = panel_mod.PANEL_PAYG[0]
    with (
        patch.dict("os.environ", {payg_spec[3]: "test-key"}),
        patch.object(panel_mod.urllib.request, "urlopen", return_value=io.BytesIO(raw)),
    ):
        result = panel_mod._http_worker(payg_spec, "task", 5)
    check("invalid UTF-8 PAYG response fails", result["success"] is False, str(result))
    check("invalid UTF-8 is malformed", result["error"] == "malformed response", str(result))


# === judge feature ==========================================================


TESTS = [
    ("test_cworker_router_unavailable", test_cworker_router_unavailable),
    (
        "test_cworker_rejects_nonzero_exit_with_stdout",
        test_cworker_rejects_nonzero_exit_with_stdout,
    ),
    ("test_cworker_accepts_zero_exit_with_stdout", test_cworker_accepts_zero_exit_with_stdout),
    ("test_cworker_rejects_oversized_stdout", test_cworker_rejects_oversized_stdout),
    ("test_http_worker_rejects_non_string_content", test_http_worker_rejects_non_string_content),
    (
        "test_safe_usage_allows_only_nonnegative_numeric_metrics",
        test_safe_usage_allows_only_nonnegative_numeric_metrics,
    ),
    ("test_http_worker_rejects_oversized_response", test_http_worker_rejects_oversized_response),
    ("test_http_worker_rejects_invalid_utf8", test_http_worker_rejects_invalid_utf8),
]
