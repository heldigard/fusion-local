# fusion-local

Multi-model deliberation (5-field consensus/contradictions/coverage gaps/unique insights/
blind spots). Public repo: https://github.com/heldigard/fusion-local

**Cross-CLI**: works identically from Claude Code, Codex, Antigravity, OpenCode (console
script on `~/.local/bin`).

## What it is

The **deliberation layer** for the big model. Two modes, same 5-field output contract:

- **fusion (DEFAULT, local)**: panel of subscription workers ($0) + cheap_llm judge
  (`deepseek-v4-flash` BYOK $0, 1M ctx) + `JUDGE_SCHEMA_PROMPT`. Cost ≈ $0–0.04.
- **fusion --openrouter**: hosted `openrouter/fusion`, every panelist searches the live
  web. PAYG, ~½ a frontier call. Use only for FRESH sources.

The big model consumes the 5-field analysis and decides — fusion returns ANALYSIS, never
a merged answer.

## Architecture (vertical-slice package)

```
src/fusion/
├── config.py       constants + cross-CLI wiring (FUSION_ROUTER, cheap_llm bootstrap)
├── panel.py        feature: lane-1 (cworker subs) + lane-2 (HTTP PAYG) + orchestration
├── judge.py        feature: 5-field schema + cheap_llm judge synthesis
├── delegate.py     feature: legacy OpenRouter hosted fusion (--openrouter)
├── cli.py          feature: fuse() + main() + FuseOptions (parameter object)
└── __init__.py     public API (fuse, run_panel, run_judge, FuseOptions, main, ...)
tests/
├── test_fusion.py     panel + judge + fuse + CLI (offline, mocked)
└── test_delegate.py   legacy payload/key/schema
```

Each module is one cohesive feature. Module/function names don't collide (`run_panel`,
`run_judge`).

## Cascade (panel → judge)

```
PANEL LANE 1 ($0 subs, parallel)   codex-spark · agy35-flash · kimic · zai
    fallback when < min_workers succeed ↓
PANEL LANE 2 (PAYG, HTTP direct)   deepseek-v4-pro · qwen3.7-max (OpenRouter)
    ↓
JUDGE  cheap_complete(cloud_model="deepseek/deepseek-v4-flash") + JUDGE_SCHEMA_PROMPT
    → 5-field JSON {consensus, contradictions, coverage_gaps, unique_insights, blind_spots}
```

## Cross-CLI wiring

- `fusion-local` console script on `~/.local/bin` (PATH of every CLI) is the canonical entry.
- `fusion` shell command = installed alias → `fusion-local`.
- **lane-1** (subs) uses `FUSION_ROUTER` (default `~/.claude/scripts/codex-worker-router.py`,
  Claude ecosystem). Non-Claude CLIs: set `FUSION_ROUTER=/your/dispatch`, or `FUSION_ROUTER=`
  to disable (panel falls back to lane-2 PAYG, universal).
- **lane-1 worker modes**: `FUSION_PANEL_SUBS` (unset = default 4 modes; `a,b` = custom;
  empty = disable lane-1). Same 3-mode semantics as `FUSION_ROUTER`.
- `--openrouter` early-delegates to `fusion.delegate.main` (legacy).

## Hardening contract (v1.2.0)

- **Judge preflight before panel spend**: `fuse()` gates on `judge.preflight()`
  (cheap_llm import + `require(CHEAP_LLM_MIN_VERSION)`) BEFORE the panel fan-out.
  `run_judge` degrades gracefully on drift or a post-panel judge transport exception,
  preserving `panel_evidence` and the structured degraded envelope.
- **Panel-side secret scrub**: `run_panel` scrubs the task via `cheap_llm.scrub_secrets`
  before lane-1/lane-2 (best-effort; judge path scrubs unconditionally inside cheap_llm).
- **Router exit-status validation**: lane-1 accepts stdout only when its dispatch process
  exits zero; partial stdout from failed dispatch is never promoted to panel evidence.
- **Exit codes** (both `--json` and readable): `0` = `judge_valid: true`, `2` = degraded.
- **Per-source timings**: successful and failed lane workers expose
  `duration_seconds` in source metadata, so timeout tuning uses evidence rather
  than total-panel latency guesses.
- **`--capabilities` live health**: `health.live` = `{cheap_llm_ok, cheap_llm_version,
  router_available, openrouter_key_present}` (local probes only; consumed by
  `cli-orchestration doctor`). `health.cheap_llm_min_version` is DRY from
  `judge.CHEAP_LLM_MIN_VERSION`.

## Entry points

- **Console scripts** (`pip install -e .`): `fusion-local` and `fusion`.
- **Wired-ecosystem shim**: `~/.claude/scripts/fusion-local.py` re-exports from the
  package (backward-compat for the Claude path).
- **Direct**: `python3 -m fusion.cli "<Q>"`.

## CLI

```
fusion "<Q>"                                  # local panel + judge (default)
fusion --json "<Q>"                           # full 5-field envelope as JSON
fusion --preset mixed "<Q>"                   # subs + augment with payg
fusion --preset cheap "<Q>"                   # low-cost OpenRouter panel
fusion --preset ultra --current-model "$MODEL" "<Q>"
fusion --cloud-model "deepseek/deepseek-v4-flash" "<Q>"
fusion --openrouter "<Q>"                     # OpenRouter hosted (web-grounded)
fusion --version
```

## Dependencies

- [`cheap-llm`](../cheap-llm) — the judge transport. Imported via `CHEAP_LLM_HOME` env
  (default `~/cheap-llm`); **no pip dependency**. `cheap_complete` provides cascade +
  secret scrub + on-disk cache.
- `codex-worker-router` (`FUSION_ROUTER`) — panel lane-1 dispatch. Optional (lane-2 is
  universal).

## Conventions

- **Vertical-slice**: feature-per-module (config/panel/judge/delegate/cli).
- `FuseOptions` dataclass — parameter object (keeps `fuse()` arity ≤ 5).
- **Secret scrub on both paths**: judge unconditionally inside cheap_llm; panel scrubs
  the task before fan-out (best-effort when cheap_llm absent on direct `run_panel`).
- **Recursion guard** on panelists: `[FUSION_PANEL][NO_DELEGATE][NO_TOOLS]`.

## Commands

- Test (offline): `python3 tests/test_fusion.py && python3 tests/test_delegate.py`
- Lint: `ruff check src/fusion/ tests/`
- Install editable: `pip install -e . --user --break-system-packages`

## Model routing

- **Panel lane 1 ($0 subs)**: `["codex-spark", "agy35-flash", "kimic", "zai"]`.
- **Panel lane 2 (PAYG fallback)**: `deepseek-v4-pro`, `qwen3.7-max`.
- **Cheap preset**: `deepseek-v4-flash`, `qwen3.7-plus`, `minimax-m3`, `mimo-v2.5-pro`.
- **Ultra preset**: `claude-fable-5`, `claude-opus-4.8`, `gpt-5.5-pro`,
  `~google/gemini-pro-latest`. GPT-5.6 is GA in OpenAI/Codex, but do not
  hardcode an OpenRouter GPT-5.6 ID until this provider-specific catalog is verified.
- **Judge**: `DEFAULT_JUDGE_MODEL = "deepseek/deepseek-v4-flash"` (override `--cloud-model`).
- **Current-model exclusion**: `--current-model` or env (`FUSION_CURRENT_MODEL`,
  `CONTROLLER_MODEL`, `CODEX_MODEL`, `ANTHROPIC_MODEL`, `GEMINI_MODEL`, `QWEN_MODEL`)
  skips matching panelists and reports them in `sources[]`.
