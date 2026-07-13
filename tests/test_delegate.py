#!/usr/bin/env python3
"""Tests for fusion.delegate — legacy OpenRouter hosted fusion.

Covers payload construction (panel/judge/reasoning/max-tokens injection),
the schema message, and the missing-API-key guard. No network.

Run: python3 tests/test_delegate.py
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
from email.message import Message
from unittest.mock import patch

from fusion import delegate

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


def _args(**kw) -> argparse.Namespace:
    """Build a fake argparse Namespace with delegate-relevant defaults."""
    base: dict[str, object] = dict(
        prompt="Q",
        panel=None,
        judge=None,
        model=None,
        required=True,
        schema=True,
        reasoning=None,
        max_tokens=None,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def test_build_payload_defaults() -> None:
    p = delegate._build_payload(_args())
    check("default model = fusion alias", p["model"] == delegate.FUSION_MODEL)
    check("plugin id fusion", p["plugins"][0]["id"] == "fusion")
    check("required → tool_choice required", p.get("tool_choice") == "required")
    check("schema injected as system msg", p["messages"][0]["role"] == "system")


def test_build_payload_panel_override() -> None:
    p = delegate._build_payload(
        _args(
            panel="anthropic/claude,gpt-latest",
            judge="judge-m",
            required=False,
            reasoning="high",
            max_tokens=4000,
        )
    )
    plug = p["plugins"][0]
    check("panel parsed to list", plug["analysis_models"] == ["anthropic/claude", "gpt-latest"])
    check("judge model set", plug["model"] == "judge-m")
    check("reasoning forwarded", plug["reasoning"] == {"effort": "high"})
    check("max_tokens forwarded", plug["max_completion_tokens"] == 4000)
    check("optional → no tool_choice", "tool_choice" not in p)


def test_build_payload_junk_panel_omitted() -> None:
    # A junk --panel (", , ") must be filtered so analysis_models is not set empty.
    p = delegate._build_payload(_args(panel=" , , "))
    check("junk panel → analysis_models omitted", "analysis_models" not in p["plugins"][0])


def test_require_key_missing_fails() -> None:
    saved = os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        try:
            delegate._require_key()
        except delegate.DelegateFailure as exc:
            check("missing key → code 1", exc.exit_code == 1, str(exc.exit_code))
            return
    finally:
        if saved is not None:
            os.environ["OPENROUTER_API_KEY"] = saved
    check("missing key raised DelegateFailure", False, "no DelegateFailure")


def test_scrubbed_prompt_override_enters_payload() -> None:
    with patch("cheap_llm.scrub_secrets", return_value="SCRUBBED"):
        scrubbed = delegate._scrub_prompt("secret prompt")
    payload = delegate._build_payload(_args(), prompt=scrubbed)
    user_messages = [m for m in payload["messages"] if m["role"] == "user"]
    check("hosted prompt scrubbed", scrubbed == "SCRUBBED", scrubbed)
    check("payload uses scrubbed prompt", user_messages[0]["content"] == "SCRUBBED")


def test_call_failure_matrix_is_safe() -> None:
    marker = "SECRET_MARKER"

    class BrokenResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size=-1):
            raise RuntimeError(marker)

    http_error = urllib.error.HTTPError(
        delegate.ENDPOINT,
        429,
        marker,
        hdrs=Message(),
        fp=io.BytesIO(marker.encode()),
    )
    failures = [
        http_error,
        urllib.error.URLError(RuntimeError(marker)),
        TimeoutError(marker),
        io.BytesIO(b"\xff"),
        io.BytesIO(b"not json"),
        BrokenResponse(),
        io.BytesIO(b"[]"),
        io.BytesIO(json.dumps({"error": {"message": marker}}).encode()),
    ]
    for failure in failures:
        patcher = (
            patch.object(delegate.urllib.request, "urlopen", side_effect=failure)
            if isinstance(failure, BaseException)
            else patch.object(delegate.urllib.request, "urlopen", return_value=failure)
        )
        with patcher:
            caught: delegate.DelegateFailure | None = None
            try:
                delegate._call({"messages": []}, "test-key", timeout_s=1)
            except delegate.DelegateFailure as exc:
                caught = exc
        check("hosted failure is typed", caught is not None and caught.exit_code == 2, repr(caught))
        message = str(caught)
        check("hosted failure is bounded", len(message) <= 300, message)
        check("hosted failure is one line", "\n" not in message, message)
        check("hosted failure hides untrusted detail", marker not in message, message)


def test_extract_text_requires_nonempty_string() -> None:
    valid = {"choices": [{"message": {"content": "answer"}}]}
    check("hosted text extracted", delegate._extract_text(valid) == "answer")
    malformed = [
        {},
        {"choices": []},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": [{"type": "text", "text": "x"}]}}]},
    ]
    for result in malformed:
        caught = False
        try:
            delegate._extract_text(result)
        except delegate.DelegateFailure as exc:
            caught = exc.exit_code == 2
        check("malformed hosted content fails", caught, str(result))


def test_call_rejects_oversized_response() -> None:
    response = io.BytesIO(b"x" * 11)
    with (
        patch.object(delegate, "MAX_EXTERNAL_RESPONSE_BYTES", 10),
        patch.object(delegate.urllib.request, "urlopen", return_value=response),
    ):
        caught: delegate.DelegateFailure | None = None
        try:
            delegate._call({"messages": []}, "test-key", timeout_s=1)
        except delegate.DelegateFailure as exc:
            caught = exc
    check("oversized hosted response is typed", caught is not None and caught.exit_code == 2)
    check(
        "oversized hosted response is stable",
        str(caught) == "hosted provider response too large",
    )


def test_main_scrub_failure_blocks_http() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
        patch("cheap_llm.scrub_secrets", side_effect=RuntimeError("SECRET_MARKER")),
        patch.object(delegate.urllib.request, "urlopen") as opener,
        patch.object(sys, "argv", ["fusion", "Q"]),
        patch.object(sys, "stdout", stdout),
        patch.object(sys, "stderr", stderr),
    ):
        rc = delegate.main()
    check("scrub failure exits 1", rc == 1, str(rc))
    check("scrub failure blocks HTTP", opener.call_count == 0, str(opener.call_count))
    check("scrub failure keeps stdout empty", stdout.getvalue() == "", stdout.getvalue())
    check("scrub failure hides detail", "SECRET_MARKER" not in stderr.getvalue(), stderr.getvalue())


def test_main_missing_key_blocks_scrub_and_http() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(delegate, "_scrub_prompt") as scrubber,
        patch.object(delegate.urllib.request, "urlopen") as opener,
        patch.object(sys, "argv", ["fusion", "Q"]),
        patch.object(sys, "stdout", stdout),
        patch.object(sys, "stderr", stderr),
    ):
        rc = delegate.main()
    check("missing key main exits 1", rc == 1, str(rc))
    check("missing key blocks scrub", scrubber.call_count == 0, str(scrubber.call_count))
    check("missing key blocks HTTP", opener.call_count == 0, str(opener.call_count))
    check("missing key stdout empty", stdout.getvalue() == "", stdout.getvalue())


def test_main_success_text_and_raw_json() -> None:
    result = {"choices": [{"message": {"content": "answer"}}], "id": "completion-1"}
    for json_mode in (False, True):
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = ["fusion", "Q", *(["--json"] if json_mode else [])]
        with (
            patch.object(delegate, "_require_key", return_value="test-key"),
            patch.object(delegate, "_scrub_prompt", return_value="SCRUBBED"),
            patch.object(delegate, "_call", return_value=result),
            patch.object(sys, "argv", argv),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
        ):
            rc = delegate.main()
        check("hosted success exits 0", rc == 0, str(rc))
        check("hosted success stderr empty", stderr.getvalue() == "", stderr.getvalue())
        if json_mode:
            check("hosted JSON stays raw", json.loads(stdout.getvalue()) == result)
        else:
            check("hosted text stays text", stdout.getvalue() == "answer\n", stdout.getvalue())


def test_main_operational_failure_has_clean_streams() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    failure = delegate.DelegateFailure("hosted transport error: TimeoutError", 2)
    with (
        patch.object(delegate, "_require_key", return_value="test-key"),
        patch.object(delegate, "_scrub_prompt", return_value="SCRUBBED"),
        patch.object(delegate, "_call", side_effect=failure),
        patch.object(sys, "argv", ["fusion", "Q", "--json"]),
        patch.object(sys, "stdout", stdout),
        patch.object(sys, "stderr", stderr),
    ):
        rc = delegate.main()
    check("hosted operational failure exits 2", rc == 2, str(rc))
    check("hosted operational stdout empty", stdout.getvalue() == "", stdout.getvalue())
    check("hosted operational stderr bounded", len(stderr.getvalue().strip()) <= 308)
    check("hosted operational no traceback", "Traceback" not in stderr.getvalue())


def test_main_rejects_nonpositive_options_before_key() -> None:
    calls: list[str] = []

    def key_recorder():
        calls.append("key")
        return "test-key"

    invalid_args = [
        ["--timeout", "0"],
        ["--max-tokens", "-1"],
        ["--panel", ", ,"],
        ["--panel", ",".join(f"model-{index}" for index in range(9))],
        ["--judge", ""],
        ["--model", " "],
    ]
    for invalid in invalid_args:
        code = None
        try:
            with (
                patch.object(delegate, "_require_key", key_recorder),
                patch.object(sys, "argv", ["fusion", "Q", *invalid]),
            ):
                delegate.main()
        except SystemExit as exc:
            code = exc.code
        check("hosted invalid option exits 2", code == 2, str((invalid, code)))
    check("hosted invalid options make zero key reads", calls == [], str(calls))


def test_judge_schema_has_five_fields() -> None:
    for field in ("Consensus", "Contradictions", "Coverage gaps", "Unique insights", "Blind spots"):
        check(f"schema names {field}", field in delegate.JUDGE_SCHEMA_PROMPT)


TESTS = [
    ("build_payload_defaults", test_build_payload_defaults),
    ("build_payload_panel_override", test_build_payload_panel_override),
    ("build_payload_junk_panel_omitted", test_build_payload_junk_panel_omitted),
    ("require_key_missing_fails", test_require_key_missing_fails),
    ("scrubbed_prompt_override_enters_payload", test_scrubbed_prompt_override_enters_payload),
    ("call_failure_matrix_is_safe", test_call_failure_matrix_is_safe),
    ("extract_text_requires_nonempty_string", test_extract_text_requires_nonempty_string),
    ("call_rejects_oversized_response", test_call_rejects_oversized_response),
    ("main_scrub_failure_blocks_http", test_main_scrub_failure_blocks_http),
    ("main_missing_key_blocks_scrub_and_http", test_main_missing_key_blocks_scrub_and_http),
    ("main_success_text_and_raw_json", test_main_success_text_and_raw_json),
    ("main_operational_failure_has_clean_streams", test_main_operational_failure_has_clean_streams),
    (
        "main_rejects_nonpositive_options_before_key",
        test_main_rejects_nonpositive_options_before_key,
    ),
    ("judge_schema_has_five_fields", test_judge_schema_has_five_fields),
]


def main() -> int:
    print(f"fusion.delegate tests — {len(TESTS)} cases\n")
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
