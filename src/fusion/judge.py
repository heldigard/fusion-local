"""Judge feature — synthesize panel responses into the 5-field schema.

Uses the cheap_llm cascade (``cheap_complete`` with ``cloud_model=``) as the
judge transport. The schema is a JSON variant of OpenRouter Fusion's 5-field
prompt (consensus / contradictions / coverage gaps / unique insights / blind
spots). ``cheap_complete`` validates the 5 required keys via ``schema_hint``.
"""

from __future__ import annotations

import json
from typing import Any

# Importing CHEAP_LLM_HOME from config triggers the cheap_llm sys.path bootstrap
# (idempotent side-effect in fusion.config) so the lazy `import cheap_llm` below resolves.
from .config import CHEAP_LLM_HOME  # noqa: F401
from .panel import summarize as _summarize_panel

DEFAULT_JUDGE_MODEL = "deepseek/deepseek-v4-flash"  # BYOK $0, 1M ctx

# Contract floor: this consumer needs the declared public API + ``cloud_model``
# param (cheap_llm SemVer >= 1.1). require() trips loudly on older installs.
_CHEAP_LLM_MIN_VERSION = "1.1"

FUSION_FIELDS: tuple[str, ...] = (
    "consensus",
    "contradictions",
    "coverage_gaps",
    "unique_insights",
    "blind_spots",
)

# JSON variant of OpenRouter Fusion's JUDGE_SCHEMA_PROMPT (same 5 fields).
JUDGE_SCHEMA_PROMPT = """You are the Fusion judge. After the panel deliberates, return your analysis as a JSON object with EXACTLY these five keys (no extra prose outside the JSON):

- "consensus": what ALL or MOST panelists agreed on (high-confidence; treat as near-fact). String.
- "contradictions": where panelists disagreed; for each, name WHICH panelist said WHAT. Array of short strings.
- "coverage_gaps": what NO panelist addressed (often the highest-value finding). Array of short strings.
- "unique_insights": non-obvious points only ONE panelist raised, worth grafting in. Array of short strings.
- "blind_spots": angles or failure modes NONE of the panelists considered. Array of short strings.

Cite the panelist driving each point. Keep the five keys distinct. If a key has no entries, return an empty array (never omit the key). Treat consensus among models with suspicion: shared training bias can make a false claim look like agreement — flag unverifiable claims."""


def empty_fields(**extra: Any) -> dict[str, Any]:
    """Return the 5-field envelope pre-filled with empty defaults, merged with extra."""
    base: dict[str, Any] = {
        "consensus": "",
        "contradictions": [],
        "coverage_gaps": [],
        "unique_insights": [],
        "blind_spots": [],
    }
    base.update(extra)
    return base


def run_judge(
    task: str,
    panel_results: list[dict[str, Any]],
    cloud_model: str | None = DEFAULT_JUDGE_MODEL,
    timeout: int = 30,
) -> dict[str, Any]:
    """Judge the panel into the 5-field schema via the cheap_llm cascade.

    Returns a dict with the 5 fusion fields plus ``judge_model`` / ``judge_valid``
    / ``cost`` / ``latency``. Degrades gracefully (parks raw text in ``consensus``)
    when the judge output is not valid JSON.
    """
    summary = _summarize_panel(panel_results)
    if not summary:
        return empty_fields(
            judge_model=None,
            judge_valid=False,
            error="no panel outputs to judge",
            sources=[],
        )

    # cheap_llm is bootstrapped onto sys.path by ``fusion.config``. The require()
    # gate declares the contract floor this consumer needs (``cloud_model``) and
    # fails fast + actionable on version drift, instead of a cryptic mid-run error.
    import cheap_llm  # type: ignore[import-not-found]  # noqa: E402

    cheap_llm.require(_CHEAP_LLM_MIN_VERSION)

    system = JUDGE_SCHEMA_PROMPT + f"\n\nPANEL RESPONSES:\n{summary}"
    res = cheap_llm.cheap_complete(
        system=system,
        prompt=task,
        schema_hint=list(FUSION_FIELDS),
        timeout_total=float(timeout),
        cloud_model=cloud_model,
        require_json=True,
    )

    parsed = _parse_judge_json(res)
    if not isinstance(parsed, dict):
        raw_text = str(res.get("text", "") or "").strip()
        return empty_fields(
            consensus=raw_text or "Judge failed; use panel_evidence for raw model signal.",
            judge_model=res.get("model"),
            judge_valid=False,
            cost=res.get("cost", 0),
            latency=res.get("latency", 0),
            error=(res.get("error") or "judge output not valid JSON"),
            panel_evidence=_panel_evidence(panel_results),
        )

    out = empty_fields()
    out["consensus"] = str(parsed.get("consensus", "") or "")
    for key in ("contradictions", "coverage_gaps", "unique_insights", "blind_spots"):
        val = parsed.get(key, [])
        out[key] = val if isinstance(val, list) else [str(val)]
    out["judge_model"] = res.get("model")
    out["judge_valid"] = True
    out["cost"] = res.get("cost", 0)
    out["latency"] = res.get("latency", 0)
    return out


def _parse_judge_json(res: dict[str, Any]) -> dict[str, Any] | None:
    """Extract a dict from the cheap_complete result, or None on failure."""
    if not (res.get("json_valid") and res.get("text")):
        return None
    try:
        return json.loads(res["text"])
    except (json.JSONDecodeError, TypeError):
        return None


def _panel_evidence(panel_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve successful panel signal when judge synthesis fails."""
    evidence: list[dict[str, Any]] = []
    for result in panel_results:
        output = str(result.get("output") or "")
        if not output:
            continue
        excerpt = output[:6000]
        evidence.append(
            {
                "source": result.get("source"),
                "lane": result.get("lane"),
                "output": excerpt,
                "output_chars": len(output),
                "truncated": len(excerpt) < len(output),
            }
        )
    return evidence
