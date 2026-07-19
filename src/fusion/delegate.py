"""Delegate feature — legacy OpenRouter hosted fusion (opt-in via --openrouter).

Every panelist searches the live web before answering; the outer model returns
assistant text (or the raw provider Chat Completion with ``--json``). PAYG on
OPENROUTER_API_KEY. Use only when the answer needs FRESH sources — otherwise
the local panel+judge is cheaper.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from ._boundary import (
    MAX_EXTERNAL_RESPONSE_BYTES,
    SecretScrubError,
    nonempty_arg,
    positive_int_arg,
    public_error,
    scrub_external_text,
)
from ._version import __version__
from .panel_models import HTTP_REFERER, HTTP_TITLE

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
FUSION_MODEL = "openrouter/fusion"
DEFAULT_TIMEOUT_S = 180  # Fusion panel+judge can run 30-120s; raise via --timeout
REQUIRE_BY_DEFAULT = os.environ.get("FUSION_REQUIRED_BY_DEFAULT", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

# Hosted presentation schema. OpenRouter's internal judge returns analysis to
# the outer model; this system message asks that outer model to expose the five
# project-standard sections instead of collapsing them into free-form prose.
JUDGE_SCHEMA_PROMPT = """You are the Fusion result presenter. After the Fusion tool deliberates, return the analysis as EXACTLY these five labeled sections, in this order:

1. **Consensus** — what all or most panelists agreed on (high-confidence; treat as near-fact).
2. **Contradictions** — where panelists disagreed; name WHICH source said WHAT.
3. **Coverage gaps** — what NO panelist addressed (often the highest-value finding).
4. **Unique insights** — non-obvious points only ONE panelist raised, worth grafting in.
5. **Blind spots** — angles or failure modes NONE of the panelists considered.

Cite the web source or panelist driving each point. Keep the five sections distinct and labeled so a downstream agent can parse them. Do NOT collapse into a single narrative."""


class DelegateFailure(RuntimeError):
    """Expected hosted-delegate failure with a stable CLI exit code."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _require_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise DelegateFailure(
            "OPENROUTER_API_KEY not set (configure it as a secrets environment variable)",
            1,
        )
    return key


def _scrub_prompt(prompt: str) -> str:
    try:
        return scrub_external_text(prompt, fail_closed=True)
    except SecretScrubError:
        raise DelegateFailure("hosted prompt scrub unavailable", 1) from None


def _build_payload(args: argparse.Namespace, prompt: str | None = None) -> dict[str, Any]:
    """Construct the Fusion request. Plugin form lets us override panel + judge."""
    messages: list[dict[str, Any]] = []
    if getattr(args, "schema", True):
        messages.append({"role": "system", "content": JUDGE_SCHEMA_PROMPT})
    messages.append({"role": "user", "content": args.prompt if prompt is None else prompt})
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
            "HTTP-Referer": HTTP_REFERER,
            "X-Title": HTTP_TITLE,
        },
    )
    try:
        # ENDPOINT is the fixed OpenRouter API URL, not user input.
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # nosemgrep
            raw = resp.read(MAX_EXTERNAL_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise DelegateFailure(public_error("hosted provider HTTP error", exc.code), 2) from None
    except urllib.error.URLError as exc:
        reason_type = type(exc.reason).__name__ if exc.reason is not None else type(exc).__name__
        raise DelegateFailure(public_error("hosted network error", reason_type), 2) from None
    except (TimeoutError, OSError) as exc:
        raise DelegateFailure(
            public_error("hosted transport error", type(exc).__name__), 2
        ) from None
    except Exception as exc:  # noqa: BLE001 — external read boundary must not traceback
        raise DelegateFailure(
            public_error("hosted transport error", type(exc).__name__), 2
        ) from None

    if not isinstance(raw, bytes):
        raise DelegateFailure("hosted provider returned invalid response bytes", 2)
    if len(raw) > MAX_EXTERNAL_RESPONSE_BYTES:
        raise DelegateFailure("hosted provider response too large", 2)
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DelegateFailure("hosted provider returned invalid JSON", 2) from None
    if not isinstance(result, dict):
        raise DelegateFailure("hosted provider returned invalid response type", 2)
    if "error" in result:
        raise DelegateFailure("hosted provider returned an error response", 2)
    return result


def _extract_text(result: dict[str, Any]) -> str:
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise DelegateFailure("hosted provider response missing assistant content", 2) from None
    if not isinstance(content, str) or not content.strip():
        raise DelegateFailure("hosted provider response has invalid assistant content", 2)
    return content


def _panel_arg(value: str) -> str:
    # OpenRouter's Fusion plugin contract allows 1-8 analysis_models.
    models = [model.strip() for model in value.split(",") if model.strip()]
    if not 1 <= len(models) <= 8:
        raise argparse.ArgumentTypeError("must contain 1 to 8 comma-separated models")
    return ",".join(models)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fusion",
        description="OpenRouter Fusion — multi-model deliberation with web grounding.",
    )
    parser.add_argument("prompt", nargs="?", help="Question to deliberate on.")
    parser.add_argument("--version", action="version", version=f"fusion-local {__version__}")
    parser.add_argument("--panel", type=_panel_arg, help="1-8 comma-separated panel models.")
    parser.add_argument(
        "--judge", type=nonempty_arg, help="Judge model that produces the structured analysis."
    )
    parser.add_argument(
        "--model", type=nonempty_arg, help="Outer model (defaults to openrouter/fusion alias)."
    )
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
    parser.add_argument(
        "--max-tokens", type=positive_int_arg, help="max_completion_tokens per inner call."
    )
    parser.add_argument(
        "--timeout", type=positive_int_arg, default=DEFAULT_TIMEOUT_S, help="Overall timeout (s)."
    )
    parser.add_argument("--json", action="store_true", help="Print the raw OpenRouter JSON.")
    args = parser.parse_args()
    if not (args.prompt or "").strip():
        parser.error("prompt must not be empty")

    try:
        key = _require_key()
        prompt = _scrub_prompt(args.prompt)
        payload = _build_payload(args, prompt=prompt)
        result = _call(payload, key, timeout_s=args.timeout)
        text = _extract_text(result)
    except DelegateFailure as exc:
        sys.stderr.write(f"fusion: {exc}\n")
        return exc.exit_code

    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
