"""Deterministic check() harness + standalone runner for the fusion gate.

Extracted from the former monolithic test_fusion.py so every per-domain slice
can share one check() (raises AssertionError on failure -> pytest gates each
slice for real) and one TESTS runner that preserves the legacy
``python3 tests/test_fusion.py`` contract.
"""

from __future__ import annotations

import json

PASS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        message = f"{name}: {detail}" if detail else name
        raise AssertionError(message)


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


def main_from(tests) -> int:
    global PASS
    PASS = 0
    fail = 0
    failures: list[str] = []
    print(f"fusion package tests — {len(tests)} cases\n")
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            fail += 1
            failures.append(f"{name}: raised {type(exc).__name__}: {exc}")
        else:
            print(f"  [ok] {name}")
    print(f"\nPASS={PASS} FAIL={fail}")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
    return 1 if fail else 0
