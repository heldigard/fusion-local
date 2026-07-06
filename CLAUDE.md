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
- `--openrouter` early-delegates to `fusion.delegate.main` (legacy).

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
- **Secret scrub inherited** from cheap_llm (judge path scrubs unconditionally).
- **Recursion guard** on panelists: `[FUSION_PANEL][NO_DELEGATE][NO_TOOLS]`.

## Commands

- Test (offline): `python3 tests/test_fusion.py && python3 tests/test_delegate.py`
- Lint: `ruff check src/fusion/ tests/`
- Install editable: `pip install -e . --user --break-system-packages`

## Model routing

- **Panel lane 1 ($0 subs)**: `["codex-spark", "agy35-flash", "kimic", "zai"]`.
- **Panel lane 2 (PAYG fallback)**: `deepseek-v4-pro`, `qwen3.7-max`.
- **Judge**: `DEFAULT_JUDGE_MODEL = "deepseek/deepseek-v4-flash"` (override `--cloud-model`).
