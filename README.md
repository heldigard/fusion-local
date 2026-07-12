# fusion-local

Multi-model **deliberation** for the big-model signal-distillation layer. Produces a
grounded 5-field structured analysis — **consensus / contradictions / coverage gaps /
unique insights / blind spots** — at a fraction of the cost of a single frontier call.

Public repo: https://github.com/heldigard/fusion-local

Graduated from `~/.claude/scripts/fusion-local.py` (2026-07-06), following the
`codeq` / `smart-trim` / `prompt-improve` / `cheap-llm` pattern. **Cross-CLI**: works identically from Claude Code, Codex, Antigravity, OpenCode.

## What it is

Two deliberation modes with the same multi-perspective goal but different wire contracts:

- **`fusion` (DEFAULT, local)** — a panel of diverse subscription workers (codex-spark /
  agy35-flash / kimic / zai — $0) drafts answers in parallel; a cheap_llm judge
  (`deepseek-v4-flash` BYOK $0, 1M ctx) synthesizes them into the 5-field schema. Falls
  back to PAYG HTTP-direct panelists if subs are exhausted. Cost ≈ **$0–0.04**.
- **`fusion --openrouter`** — the hosted `openrouter/fusion` model where every panelist
  searches the live web before answering. Use when the answer needs FRESH sources
  (current APIs, recent CVEs, "2026 state of X"). PAYG, ~½ a frontier call. Default
  output is assistant text; `--json` is the raw OpenRouter Chat Completion, not the
  local Fusion envelope.

In local mode, the controller consumes the strict 5-field analysis and makes the final
call. In hosted mode, OpenRouter's outer model consumes its internal Fusion analysis and
returns assistant text (requested as five labeled sections by this CLI).

## Architecture (vertical-slice package)

```
src/fusion/
├── _boundary.py   shared input/error/scrub contracts for external boundaries
├── _version.py    canonical installed-version resolution
├── config.py       constants + cross-CLI wiring (FUSION_ROUTER, cheap_llm bootstrap)
├── panel.py        feature: lane-1 (cworker subs) + lane-2 (HTTP PAYG) + orchestration
├── judge.py        feature: 5-field schema + cheap_llm judge synthesis
├── delegate.py     feature: legacy OpenRouter hosted fusion (--openrouter)
├── cli.py          feature: fuse() + main() + FuseOptions (parameter object)
└── __init__.py     public API
tests/
├── test_fusion.py     panel + judge + fuse + CLI contracts (offline, mocked)
└── test_delegate.py   hosted payload/transport/stream/exit contracts (offline, mocked)
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

Lane-1 **worker modes** are overridable the same way: `FUSION_PANEL_SUBS` unset →
default (`codex-spark,agy35-flash,kimic,zai`); `FUSION_PANEL_SUBS=a,b` → custom
modes for your dispatch; `FUSION_PANEL_SUBS=` (empty) → disable lane-1.

| CLI | `fusion` command | lane-1 ($0 subs) | lane-2 (PAYG) |
|-----|------------------|------------------|---------------|
| Claude Code | ✓ | ✓ (codex-worker-router) | ✓ |
| Codex | ✓ | fallback → lane-2 (or set `FUSION_ROUTER`) | ✓ |
| Antigravity | ✓ | fallback → lane-2 | ✓ |
| OpenCode | ✓ | fallback → lane-2 | ✓ |

## Entry points

- **Console script** (`pip install -e .`): `fusion-local` (canonical, cross-CLI).
- **`fusion` shell command**: installed alias → `fusion-local`.
- **Wired-ecosystem shim**: `~/.claude/scripts/fusion-local.py` re-exports from the
  package (backward-compat for the Claude path).
- **Direct**: `python3 -m fusion.cli "<Q>"`.

## CLI

```
fusion "<Q>"                                  # local panel + judge (default)
fusion --json "<Q>"                           # full 5-field envelope as JSON
fusion --preset mixed "<Q>"                   # always run subs + default PAYG panel
fusion --preset cheap "<Q>"                   # low-cost OpenRouter panel
fusion --preset ultra --current-model "$MODEL" "<Q>"
fusion --cloud-model "deepseek/deepseek-v4-flash" "<Q>"
fusion --openrouter "<Q>"                     # OpenRouter hosted (web-grounded)
fusion --openrouter --panel "anthropic/claude-opus-latest,openai/gpt-latest" "<Q>"
fusion --openrouter --json "<Q>"              # raw OpenRouter Chat Completion JSON
fusion-local --capabilities                   # JSON contract for routers/doctors
fusion --version
```

`--openrouter` early-delegates to `delegate.main` with all args intact. Hosted
`--help`/`--version` need no prompt or key; `--panel` accepts 1–8 models; positive
timeouts/token limits are validated before key lookup, scrub, or HTTP.
`--capabilities` emits a schema-versioned, self-contained manifest with invocation,
inputs, prerequisites, output formats, recovery, exit codes, safety hints, presets,
and health metadata — including **live probes** (`health.live`: cheap_llm
availability/version, router presence, OpenRouter key presence as booleans);
it is for `cli-orchestration doctor`, routers, and workers, not for the
deliberation hot path.

**Local exit codes** (both `--json` and readable): `0` = valid strict 5-field synthesis
(`judge_valid: true`), `2` = degraded (`error` + optional `panel_evidence`).

**Hosted exit codes:** `0` = usable assistant response, `1` = missing key or fail-closed
prompt scrub unavailable, `2` = invalid usage or provider/network/malformed response.
Hosted failures keep stdout empty and diagnostics bounded on stderr.

## Conventions

- **Vertical-slice package**: each feature is one module (config / panel / judge /
  delegate / cli), with `_boundary` and `_version` as small shared contract modules.
  `FuseOptions` is a parameter object (keeps `fuse()` arity ≤ 5).
- Module/function names don't collide (`run_panel`, `run_judge` — not `panel.panel`).
- The judge is `cheap_complete(cloud_model="deepseek-v4-flash")` — never a frontier
  model. Quality comes from the 5-field schema + a 1M-ctx economical judge.
- **Secret scrub at every third-party boundary**: the judge inherits it from cheap_llm
  (`scrub_secrets` via `cheap_complete`); the panel scrubs the task itself before
  fanning out to lane-1/lane-2 workers (best-effort — identity when cheap_llm is
  absent and `run_panel` is called directly); hosted `--openrouter` fails closed if its
  prompt cannot be scrubbed.
- **Validate before spend**: public APIs reject blank tasks, unknown presets, invalid
  option objects, and non-positive strict integers with `ValueError`; CLIs reject the
  same inputs through argparse before preflight or dispatch. Explicit `mixed` always
  runs subscription and PAYG lanes.
- **Strict judge schema**: exactly the five keys, `consensus: str`, four `list[str]`
  fields, and no duplicate JSON keys. Malformed results degrade without coercion.
- **Safe public errors**: envelopes/sources/stderr use stable one-line diagnostics of at
  most 300 characters and never include provider bodies, stderr, exception messages,
  prompts, headers, or partial stdout.
- **Bounded HTTP responses**: panel and hosted provider bodies are capped at 4 MiB before
  decoding, preventing malformed endpoints from causing unbounded in-memory reads.
- **Judge preflight before panel spend**: `fuse()` gates on the cheap_llm contract
  (import + `require(>=1.1.1)`) BEFORE fanning out the panel, so a missing/drifted
  judge transport fails with an actionable error instead of after PAYG spend.
  `run_judge` also degrades gracefully when the judge transport raises after the
  panel completes, preserving `panel_evidence` and the CLI's structured exit-2 envelope.
- **Router exit-status validation**: lane-1 accepts stdout only from a zero-exit router;
  partial stdout from a failed process is discarded rather than judged as evidence.
- **Recursion guard** on panelists: `[FUSION_PANEL][NO_DELEGATE][NO_TOOLS]`.

## Commands

- Test (offline): `python3 tests/test_fusion.py && python3 tests/test_delegate.py`
- Lint: `ruff check src/fusion/ tests/`
- Install editable: `pip install -e . --user --break-system-packages` (exposes `fusion-local` and `fusion`)

## Model routing

- **Panel lane 1 ($0 subs)**: `codex-spark`, `agy35-flash`, `kimic`, `zai` (cross-family).
- **Panel lane 2 (PAYG fallback)**: `deepseek-v4-pro`, `qwen3.7-max` (OpenRouter HTTP).
- **Mixed preset**: all configured subscription workers plus the default PAYG panel.
- **Cheap preset**: `deepseek-v4-flash`, `qwen3.7-plus`, `minimax-m3`, `mimo-v2.5-pro`.
- **Ultra preset**: `claude-fable-5`, `claude-opus-4.8`, `gpt-5.5-pro`,
  `~google/gemini-pro-latest`. GPT-5.6 is GA in OpenAI/Codex, but no OpenRouter
  GPT-5.6 ID is used until its provider-specific catalog is verified.
- **Judge**: `deepseek/deepseek-v4-flash` (BYOK $0, 1M ctx) via cheap_llm cascade.
- **Current-model exclusion**: pass `--current-model`, or set `FUSION_CURRENT_MODEL`,
  `CONTROLLER_MODEL`, `CODEX_MODEL`, `ANTHROPIC_MODEL`, `GEMINI_MODEL`, or `QWEN_MODEL`.
  Matching panelists are skipped and reported in `sources[]` so the controller does not
  ask the same model to validate itself.
