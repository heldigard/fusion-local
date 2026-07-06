"""Delegate feature — legacy OpenRouter hosted fusion (opt-in via --openrouter).

Every panelist searches the live web before answering; a judge returns the same
5-field analysis. PAYG on OPENROUTER_API_KEY. Use only when the answer needs
FRESH sources (current APIs, recent CVEs, "2026 state of X") — otherwise the
local panel+judge is cheaper.

Self-contained: its own argparse + HTTP transport, no dependency on the rest of
the package (graduated verbatim from the original ``~/.claude/scripts/fusion.py``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
FUSION_MODEL = "openrouter/fusion"
DEFAULT_TIMEOUT_S = 180  # Fusion panel+judge can run 30-120s; raise via --timeout
REQUIRE_BY_DEFAULT = os.environ.get("FUSION_REQUIRED_BY_DEFAULT", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

# 5-field judge schema — the structured-analysis contract at the heart of the
# deliberation architecture. Injected as a system message so the judge RETURNS
# this shape instead of free-form prose.
JUDGE_SCHEMA_PROMPT = """You are the Fusion judge. After the panel deliberates, return your analysis as EXACTLY these five labeled sections, in this order:

1. **Consensus** — what all or most panelists agreed on (high-confidence; treat as near-fact).
2. **Contradictions** — where panelists disagreed; name WHICH source said WHAT.
3. **Coverage gaps** — what NO panelist addressed (often the highest-value finding).
4. **Unique insights** — non-obvious points only ONE panelist raised, worth grafting in.
5. **Blind spots** — angles or failure modes NONE of the panelists considered.

Cite the web source or panelist driving each point. Keep the five sections distinct and labeled so a downstream agent can parse them. Do NOT collapse into a single narrative."""


def _require_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        sys.stderr.write(
            "fusion: OPENROUTER_API_KEY not set. Add to ~/.zshrc (secrets env-var only).\n"
        )
        sys.exit(1)
    return key


def _build_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Construct the Fusion request. Plugin form lets us override panel + judge."""
    messages: list[dict[str, Any]] = []
    if getattr(args, "schema", True):
        messages.append({"role": "system", "content": JUDGE_SCHEMA_PROMPT})
    messages.append({"role": "user", "content": args.prompt})
    payload: dict[str, Any] = {"model": FUSION_MODEL, "messages": messages}

    plugins: list[dict[str, Any]] = [{"id": "fusion"}]
    if args.panel:
        models = [m.strip() for m in args.panel.split(",") if m.strip()]
        if models:
            plugins[0]["analysis_models"] = models
    if args.judge:
        plugins[0]["model"] = args.judge
    if args.max_tokens:
        plugins[0]["max_completion_tokens"] = args.max_tokens
    if args.reasoning:
        plugins[0]["reasoning"] = {"effort": args.reasoning}
    payload["plugins"] = plugins

    if args.required:
        payload["tool_choice"] = "required"
    if args.model:
        payload["model"] = args.model
    return payload


def _call(payload: dict[str, Any], key: str, timeout_s: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://claude.local/fusion",
            "X-Title": "fusion",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        sys.stderr.write(f"fusion: HTTP {exc.code} from OpenRouter:\n{body}\n")
        sys.exit(2)
    except urllib.error.URLError as exc:
        sys.stderr.write(f"fusion: network error: {exc.reason}\n")
        sys.exit(2)


def _extract_text(result: dict[str, Any]) -> str:
    try:
        return result["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return json.dumps(result, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fusion",
        description="OpenRouter Fusion — multi-model deliberation with web grounding.",
    )
    parser.add_argument("prompt", help="Question to deliberate on.")
    parser.add_argument("--panel", help="Comma-separated analysis_models (panel).")
    parser.add_argument("--judge", help="Judge model that produces the structured analysis.")
    parser.add_argument("--model", help="Outer model (defaults to openrouter/fusion alias).")
    parser.add_argument(
        "--required",
        action="store_true",
        default=REQUIRE_BY_DEFAULT,
        help="Force deliberation on every request (tool_choice=required).",
    )
    parser.add_argument(
        "--optional",
        dest="required",
        action="store_false",
        help="Allow the outer model to answer without invoking Fusion.",
    )
    parser.add_argument(
        "--schema",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Inject the 5-field judge schema as a system message. Default on.",
    )
    parser.add_argument(
        "--reasoning",
        choices=["minimal", "low", "medium", "high"],
        help="Reasoning effort forwarded to panel + judge.",
    )
    parser.add_argument("--max-tokens", type=int, help="max_completion_tokens per inner call.")
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Overall timeout (s)."
    )
    parser.add_argument("--json", action="store_true", help="Print the raw OpenRouter JSON.")
    args = parser.parse_args()

    key = _require_key()
    payload = _build_payload(args)
    result = _call(payload, key, timeout_s=args.timeout)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        text = _extract_text(result)
        print(text if text else json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
