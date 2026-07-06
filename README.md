# fusion-cli

Multi-model **deliberation** for the big-model signal-distillation layer. Produces a
grounded 5-field structured analysis — **consensus / contradictions / coverage gaps /
unique insights / blind spots** — at a fraction of the cost of a single frontier call.

Public repo: https://github.com/heldigard/fusion-local

Graduated from `~/.claude/scripts/fusion-local.py` + `~/.claude/scripts/fusion.py`
(2026-07-06), following the `codeq` / `smart-trim` / `prompt-improve` / `cheap-llm`
pattern. **Cross-CLI**: works identically from Claude Code, Codex, Antigravity, OpenCode.

## What it is

Two deliberation modes, **same 5-field output contract**:

- **`fusion` (DEFAULT, local)** — a panel of diverse subscription workers (codex-spark /
  agy35-flash / kimic / zai — $0) drafts answers in parallel; a cheap_llm judge
  (`deepseek-v4-flash` BYOK $0, 1M ctx) synthesizes them into the 5-field schema. Falls
  back to PAYG HTTP-direct panelists if subs are exhausted. Cost ≈ **$0–0.04**.
- **`fusion --openrouter`** — the hosted `openrouter/fusion` model where every panelist
  searches the live web before answering. Use when the answer needs FRESH sources
  (current APIs, recent CVEs, "2026 state of X"). PAYG, ~½ a frontier call.

The brain (big model) consumes the 5-field output and makes the final call — fusion
returns ANALYSIS, never a merged answer.

## Architecture (vertical-slice package)

```
src/fusion/
├── config.py       constants + cross-CLI wiring (FUSION_ROUTER, cheap_llm bootstrap)
├── panel.py        feature: lane-1 (cworker subs) + lane-2 (HTTP PAYG) + orchestration
├── judge.py        feature: 5-field schema + cheap_llm judge synthesis
├── delegate.py     feature: legacy OpenRouter hosted fusion (--openrouter)
├── cli.py          feature: fuse() + main() + FuseOptions (parameter object)
└── __init__.py     public API
tests/
├── test_fusion.py     panel + judge + fuse + CLI (offline, mocked)
└── test_delegate.py   legacy payload/key/schema
```

Each module is one cohesive feature (≤5 params/fn, shallow nesting). The judge reuses
the [`cheap-llm`](../cheap-llm) cascade (`cheap_complete` with `cloud_model=`), imported
via `CHEAP_LLM_HOME` — no pip dependency.

## Cross-CLI usage (Claude Code, Codex, Antigravity, OpenCode)

`fusion-local` is a **console script** on `~/.local/bin` (in every CLI's PATH). All four
CLIs invoke it identically:

```bash
fusion "<question>"                     # works from any CLI
fusion --json "<Q>" | jq .consensus
fusion --openrouter "<Q>"               # web-grounded (OpenRouter)
```

Panel **lane-1** (subscription workers, $0) routes through the codex-worker-router
(Claude ecosystem). Non-Claude CLIs without that router:
- automatically fall back to **lane-2** (PAYG HTTP direct, universal), **or**
- set `FUSION_ROUTER=/path/to/your/dispatch` to wire lane-1 to your own dispatch, **or**
- set `FUSION_ROUTER=` (empty) to disable lane-1 entirely.

| CLI | `fusion` command | lane-1 ($0 subs) | lane-2 (PAYG) |
|-----|------------------|------------------|---------------|
| Claude Code | ✓ | ✓ (codex-worker-router) | ✓ |
| Codex | ✓ | fallback → lane-2 (or set `FUSION_ROUTER`) | ✓ |
| Antigravity | ✓ | fallback → lane-2 | ✓ |
| OpenCode | ✓ | fallback → lane-2 | ✓ |

## Entry points

- **Console script** (`pip install -e .`): `fusion-local` (canonical, cross-CLI).
- **`fusion` shell command**: symlink → `fusion-local` (on `~/.local/bin`).
- **Wired-ecosystem shims**: `~/.claude/scripts/fusion-local.py` + `fusion.py` re-export
  from the package (backward-compat for the Claude path).
- **Direct**: `python3 -m fusion.cli "<Q>"`.

## CLI

```
fusion "<Q>"                                  # local panel + judge (default)
fusion --json "<Q>"                           # full 5-field envelope as JSON
fusion --preset mixed "<Q>"                   # subs + augment with payg
fusion --cloud-model "deepseek/deepseek-v4-flash" "<Q>"
fusion --openrouter "<Q>"                     # OpenRouter hosted (web-grounded)
fusion --openrouter --panel "anthropic/claude-opus-latest,openai/gpt-latest" "<Q>"
fusion --version
```

`--openrouter` early-delegates to `delegate.main` with all args intact (legacy
`--help`/`--panel`/`--max-tokens` work as if called directly).

## Conventions

- **Vertical-slice package**: each feature is one module (config / panel / judge /
  delegate / cli). `FuseOptions` is a parameter object (keeps `fuse()` arity ≤ 5).
- Module/function names don't collide (`run_panel`, `run_judge` — not `panel.panel`).
- The judge is `cheap_complete(cloud_model="deepseek-v4-flash")` — never a frontier
  model. Quality comes from the 5-field schema + a 1M-ctx economical judge.
- **Secret scrub is inherited** from cheap_llm (`scrub_secrets` via `cheap_complete`).
- **Recursion guard** on panelists: `[FUSION_PANEL][NO_DELEGATE][NO_TOOLS]`.

## Commands

- Test (offline): `python3 tests/test_fusion.py && python3 tests/test_delegate.py`
- Lint: `ruff check src/fusion/ tests/`
- Install editable: `pip install -e . --user --break-system-packages` (exposes `fusion-local`)

## Model routing

- **Panel lane 1 ($0 subs)**: `codex-spark`, `agy35-flash`, `kimic`, `zai` (cross-family).
- **Panel lane 2 (PAYG fallback)**: `deepseek-reasoner`, `or-qwenc-max` (OpenRouter HTTP).
- **Judge**: `deepseek/deepseek-v4-flash` (BYOK $0, 1M ctx) via cheap_llm cascade.
