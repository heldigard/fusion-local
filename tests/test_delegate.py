#!/usr/bin/env python3
"""Tests for fusion.delegate — legacy OpenRouter hosted fusion.

Covers payload construction (panel/judge/reasoning/max-tokens injection),
the schema message, and the missing-API-key guard. No network.

Run: python3 tests/test_delegate.py
"""

from __future__ import annotations

import argparse

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


def test_require_key_missing_exits() -> None:
    import os

    saved = os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        try:
            delegate._require_key()
        except SystemExit as exc:
            check("missing key → exit 1", exc.code == 1, str(exc.code))
            return
    finally:
        if saved is not None:
            os.environ["OPENROUTER_API_KEY"] = saved
    check("missing key raised SystemExit", False, "no SystemExit")


def test_judge_schema_has_five_fields() -> None:
    for field in ("Consensus", "Contradictions", "Coverage gaps", "Unique insights", "Blind spots"):
        check(f"schema names {field}", field in delegate.JUDGE_SCHEMA_PROMPT)


TESTS = [
    ("build_payload_defaults", test_build_payload_defaults),
    ("build_payload_panel_override", test_build_payload_panel_override),
    ("build_payload_junk_panel_omitted", test_build_payload_junk_panel_omitted),
    ("require_key_missing_exits", test_require_key_missing_exits),
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
