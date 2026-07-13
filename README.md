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
  agy35-flash / kimic / zai — $0) drafts answers in parallel; a local-first cheap_llm
  judge with `deepseek-v4-flash` as its T2 fallback synthesizes the 5-field schema. Falls
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

Each module is one cohesive feature with bounded public signatures and shallow nesting. The judge reuses
the [`cheap-llm`](../cheap-llm) cascade (`cheap_complete` with a pinned T2
`cloud_model=` fallback), imported
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

The first-party router uses `fusion-panel-v1`: answer-only stdout, no tools, no
router-level cloud fallback, and bounded output. Fusion owns all lane-2/PAYG
decisions, so a nominal subscription seat cannot silently become a cloud worker.

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
fusion --preset intelligence "<Q>"            # frontier-accessible (medium-high complexity)
fusion --preset ultra --current-model "$MODEL" "<Q>"  # full frontier (high-stakes only)
fusion --preset ultra --cloud-judge --cloud-model deepseek/deepseek-v4-pro "<Q>"
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
with final quorum (`judge_valid: true`), `2` = degraded (`error`, `panel_quorum`,
and optional `panel_evidence`). JSON also carries `schema_version`, `status`, safe
per-source usage/timing metadata, and `total_known_cost` when providers report it.

**Hosted exit codes:** `0` = usable assistant response, `1` = missing key or fail-closed
prompt scrub unavailable, `2` = invalid usage or provider/network/malformed response.
Hosted failures keep stdout empty and diagnostics bounded on stderr.

## Conventions

- **Vertical-slice package**: each feature is one module (config / panel / judge /
  delegate / cli), with `_boundary` and `_version` as small shared contract modules.
  `FuseOptions` is a parameter object (keeps `fuse()` arity ≤ 5).
- Module/function names don't collide (`run_panel`, `run_judge` — not `panel.panel`).
- The judge is local-first with `deepseek/deepseek-v4-flash` pinned as its T2
  fallback — never a frontier panel seat. For a high-stakes synthesis, use
  `--cloud-judge --cloud-model deepseek/deepseek-v4-pro`; the model is explicit
  so Fusion never adds spend silently based on the preset.
- **Secret scrub at every third-party boundary**: the judge inherits it from cheap_llm
  (`scrub_secrets` via `cheap_complete`); the panel scrubs the task itself before
  fanning out to lane-1/lane-2 workers. Local and hosted paths fail closed before
  dispatch if their prompt cannot be scrubbed.
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
- **Final quorum**: `min_workers` is both the subscription-fallback threshold and the
  minimum successful-output count before judge synthesis. Set `--min-workers 1`
  explicitly only when a single-seat result is intentional.
- **Judge injection boundary**: bounded panel answers are serialized as untrusted JSON
  in the judge user message, never concatenated into the judge system policy.
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
- **Intelligence preset**: `x-ai/grok-4.5`, `~google/gemini-pro-latest`,
  `openai/gpt-5.6-terra`, `deepseek/deepseek-v4-pro`. Frontier-accessible, 4
  families, NO premium $25–50/M seats — for medium-high complexity without the
  ultra tax (~5x cheaper than ultra).
- **Ultra preset**: `claude-fable-5`, `claude-opus-4.8`, `gpt-5.6-sol-pro`,
  `~google/gemini-pro-latest`, `x-ai/grok-4.5`. GPT-5.6 Sol Pro and Grok 4.5
  verified in the live OpenRouter catalog (2026-07-12); legacy `gpt-5.5-pro`
  dropped. Gemini stays on the `~google/gemini-pro-latest` alias (no pinned pro
  ID is exposed beyond it).
- **Judge**: local-first cheap_llm cascade with `deepseek/deepseek-v4-flash`
  (1M ctx) pinned as T2 fallback; explicit `--cloud-judge` skips T1.
- **Current-model exclusion**: pass `--current-model`, or set `FUSION_CURRENT_MODEL`,
  `CONTROLLER_MODEL`, or the CLI-specific model env. Claude sessions fall back
  to `~/.claude/settings.json`; Codex sessions fall back to the root `model` in
  `~/.codex/config.toml`. Other harnesses can use `ANTIGRAVITY_MODEL`,
  `OPENCODE_MODEL`, `KIMI_MODEL`, or `QWEN_MODEL`.
  Matching panelists are skipped and reported in `sources[]` so the controller does not
  ask the same model to validate itself.

## Preset selection by complexity

Cost is output $/M tokens (live OpenRouter, 2026-07-12). The controller decides
when to invoke fusion and which preset fits the stakes — fusion itself never
auto-invokes. Pick the cheapest panel whose downside-risk you can tolerate.

| Preset | Seats | Output $/M | Use when | Avoid when |
|---|---|---|---|---|
| `subs` | 4 | $0 | default first pass; subs quota available | quota exhausted / no `FUSION_ROUTER` |
| `cheap` | 4 | $0.15–1.28 | low-stakes sanity check, routine second opinion | irreversible / security / architecture |
| `payg` | 2 | $0.87–3.75 | general deliberation, open-capable diversity | need frontier reasoning depth |
| `intelligence` | 4 | $6–15 | medium-high: design tradeoffs, hard bugs, unfamiliar APIs | trivial (waste) or irreversible (use ultra) |
| `ultra` | 5 | $6–50 | HIGH-STAKES: migrations, security/auth, prod, irreversible architecture | reversible / low-complexity — premium seats burn budget |
| `mixed` | 6 | $0–3.75 | subs diversity AND a PAYG floor | tight cost budget |

**Rule of thumb:** escalate `cheap → payg → intelligence → ultra` only when the
cost of being wrong exceeds the cost of the extra completions. `ultra`'s premium
seats (fable-5, sol-pro, opus-4.8) are for irreversible/high-stakes work; for
medium-high complexity use `intelligence` (frontier voices without the premium
tax).
