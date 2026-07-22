# fusion-local

Multi-model **deliberation** for the big-model signal-distillation layer. Produces a
grounded 5-field structured analysis — **consensus / contradictions / coverage gaps /
unique insights / blind spots** — at a fraction of the cost of a single frontier call.

Public repo: https://github.com/heldigard/fusion-local

Current model evidence and promotion gates:
[`docs/model-routing-audit-2026-07-19.md`](docs/model-routing-audit-2026-07-19.md).

Graduated from `~/.claude/scripts/fusion-local.py` (2026-07-06), following the
`codeq` / `smart-trim` / `prompt-improve` / `cheap-llm` pattern. **Cross-CLI**: works identically from Claude Code, Codex, Antigravity, OpenCode.

## What it is

Two deliberation modes with the same multi-perspective goal but different wire contracts:

- **`fusion` (DEFAULT, local)** — a task-specific panel of subscription workers ($0)
  drafts answers in parallel; a local-only cheap_llm judge synthesizes the 5-field
  schema. The `subs` preset never enters PAYG unless `--allow-payg-fallback` is
  explicit. Default known API cost is **$0**.
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
├── _boundary.py     shared input/error/scrub contracts for external boundaries
├── _version.py      canonical installed-version resolution
├── config.py        constants + cross-CLI wiring (FUSION_ROUTER, cheap_llm bootstrap)
├── panel_models.py  model catalog: types, presets, MODEL_ALIASES, WORKER_GUARD (pure data)
├── panel_current.py current-controller detection + panel-seat exclusion/matching
├── panel.py         feature: lane-1 (cworker subs) + lane-2 (HTTP PAYG) + orchestration
├── judge.py         feature: 5-field schema + cheap_llm judge synthesis
├── delegate.py      feature: legacy OpenRouter hosted fusion (--openrouter)
├── cli.py           feature: fuse() + main() + FuseOptions (parameter object)
├── capabilities.py  machine-readable capability manifest (doctor/router consumer)
└── __init__.py      public API
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
- degrade without spending by default, **or**
- pass `--allow-payg-fallback` to authorize **lane-2** and T2 judge fallback, **or**
- set `FUSION_ROUTER=/path/to/your/dispatch` to wire lane-1 to your own dispatch, **or**
- set `FUSION_ROUTER=` (empty) to disable lane-1 entirely.

The first-party router uses `fusion-panel-v1`: answer-only stdout, no tools, no
router-level cloud fallback, and bounded output. Fusion owns all lane-2/PAYG
decisions, so a nominal subscription seat cannot silently become a cloud worker.

Lane-1 defaults to the `balanced` profile. Select another with
`--subs-profile coding|reasoning|fast|specialists` or `FUSION_SUBS_PROFILE`; an explicit
`FUSION_PANEL_SUBS=a,b` worker list has highest precedence. Set
`FUSION_PANEL_SUBS=` (empty) to disable lane-1.

| CLI | `fusion` command | lane-1 ($0 subs) | lane-2 (PAYG) |
|-----|------------------|------------------|---------------|
| Claude Code | ✓ | ✓ (codex-worker-router) | ✓ |
| Codex | ✓ | ✓ through the shared router | explicit only |
| Antigravity | ✓ | ✓ through the shared router | explicit only |
| OpenCode | ✓ | ✓ through the shared router | explicit only |

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
fusion --subs-profile coding "<Q>"            # code specialists, subscriptions only
fusion --subs-profile reasoning --panel-timeout 480 "<Q>"  # frontier subscription hands
fusion --subs-profile fast "<Q>"              # bounded high-volume validation
fusion --subs-profile specialists "<Q>"       # Kimi/GLM/MiMo/Grok diversity
fusion --allow-payg-fallback "<Q>"            # authorize PAYG only after subs/local failure
fusion --preset mixed "<Q>"                   # always run subs + default PAYG panel
fusion --preset cheap "<Q>"                   # low-cost direct-provider panel
fusion --preset intelligence "<Q>"            # frontier-accessible (medium-high complexity)
fusion --preset ultra --current-model "$MODEL" "<Q>"  # full frontier (high-stakes only)
fusion --preset ultra "<Q>"                  # strong v4-pro cloud judge is automatic
fusion --allow-payg-fallback --cloud-model "deepseek/deepseek-v4-flash" "<Q>"
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
- The `subs` judge is local-only by default. `deepseek/deepseek-v4-flash` is the
  pinned T2 fallback only after `--allow-payg-fallback`. Frontier presets scale the
  judge with the panel: `ultra`/`intelligence` default to the strong cloud judge
  `deepseek/deepseek-v4-pro` (cloud-only, metered like their seats). Any preset
  accepts explicit `--cloud-judge`/`--cloud-model` overrides.
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
  (import + `require(>=1.4.0)`) BEFORE fanning out the panel, so a missing/drifted
  judge transport fails with an actionable error instead of after PAYG spend.
  `run_judge` also degrades gracefully when the judge transport raises after the
  panel completes, preserving `panel_evidence` and the CLI's structured exit-2 envelope.
- **Router exit-status validation**: lane-1 accepts stdout only from a zero-exit router;
  partial stdout from a failed process is discarded rather than judged as evidence.
- **Final quorum**: `min_workers` is the minimum successful-output count before
  judge synthesis and, only with `--allow-payg-fallback`, the subscription fallback
  threshold. Set `--min-workers 1`
  explicitly only when a single-seat result is intentional.
- **Judge injection boundary**: bounded panel answers are serialized as untrusted JSON
  in the judge user message, never concatenated into the judge system policy.
- **Recursion guard** on panelists: `[FUSION_PANEL][NO_DELEGATE][NO_TOOLS]`.

## Commands

- Test (offline): `python3 tests/test_fusion.py && python3 tests/test_delegate.py`
- Lint: `ruff check src/fusion/ tests/`
- Install editable: `pip install -e . --user --break-system-packages` (exposes `fusion-local` and `fusion`)

## Model routing

- **Panel lane 1 ($0 subs)** uses explicit task profiles:
  - `balanced`: Claude Sonnet 5, Kimi K3, GLM 5.2; three live-verified families.
  - `coding`: GPT-5.6 Terra, Claude Sonnet 5, Kimi K3, Grok Build.
  - `reasoning`: Claude Opus 4.8, GPT-5.6 Sol, Gemini 3.5 Flash, Kimi K3, GLM 5.2.
  - `fast`: GPT-5.6 Luna, Gemini 3.5 Flash, GLM 5.2.
  - `specialists`: Kimi K3, GLM 5.2, MiMo V2.5 Pro, Grok Build.
  MiniMax M2.7 is excluded because M3 supersedes it; its subscription seat
  remains manual via `FUSION_PANEL_SUBS=mini`. MiMo stays opt-in, and Grok Build
  is treated as a coding specialist rather than as Grok 4.5.
  Live protocol checks confirmed direct Claude Fable/Sonnet/Opus and
  Antigravity Gemini 3.5 Flash, Gemini 3.1 Pro, Claude Opus 4.6, and Claude
  Sonnet 4.6. Fable's response does not imply subscription coverage: after
  2026-07-07 Anthropic meters it through usage credits, so Fusion rejects
  `claude-fable` from lane 1 and exposes it only through the explicit PAYG
  `ultra` preset. The Antigravity Claude seats remain manual because the newer
  direct-Claude seats dominate them.
- **Panel lane 2 (explicit PAYG fallback/presets)**: `deepseek-v4-pro` (first-party
  `api.deepseek.com` since 2026-07-17 — same weights, no OpenRouter markup),
  `qwen3.7-max` (ZenMux, lower verified listing price).
- **Mixed preset**: all configured subscription workers plus the default PAYG panel.
- **Cheap preset**: `deepseek-v4-flash` (DeepInfra) + `minimax-m3` (ZenMux).
  Qwen Plus and MiMo were removed because they did not add enough quality or
  agentic strength to justify doubling panel and judge-input tokens.
- **Intelligence preset**: `x-ai/grok-4.5`, `openai/gpt-5.6-terra`, `z-ai/glm-5.2`.
  Three strong families without premium Fable/Sol-Pro seats.
- **Ultra preset**: `claude-fable-5`, `gpt-5.6-sol-pro`, `x-ai/grok-4.5`.
  Opus 4.8 was removed because Fable 5 dominates it within Anthropic; the
  weaker Gemini Pro slot was also removed.
- **Judge**: local-only for default `subs`; `--allow-payg-fallback` enables its pinned
  `deepseek/deepseek-v4-flash` T2. The explicitly metered `intelligence`/`ultra`
  presets default to the cloud-only `deepseek/deepseek-v4-pro` judge; on other
  presets, explicit `--cloud-judge` skips T1.
- **Current-model exclusion**: pass `--current-model`, or set `FUSION_CURRENT_MODEL`,
  `CONTROLLER_MODEL`, or the CLI-specific model env. Claude sessions fall back
  to `~/.claude/settings.json`; Codex sessions fall back to the root `model` in
  `~/.codex/config.toml`. Other harnesses can use `ANTIGRAVITY_MODEL`,
  `OPENCODE_MODEL`, `KIMI_MODEL`, or `QWEN_MODEL`.
  Matching panelists are skipped and reported in `sources[]` so the controller does not
  ask the same model to validate itself.

## Preset selection by complexity

Cost is output $/M tokens (live provider catalogs, 2026-07-19). The controller decides
when to invoke fusion and which preset fits the stakes — fusion itself never
auto-invokes. Pick the cheapest panel whose downside-risk you can tolerate.

| Preset | Seats | Output $/M | Use when | Avoid when |
|---|---|---|---|---|
| `subs` | 3–5 | $0 | task-specific first pass; subs quota available | quota exhausted / no `FUSION_ROUTER` |
| `cheap` | 2 | $0.18–1.10 | low-stakes sanity check, routine second opinion | irreversible / security / architecture |
| `payg` | 2 | $0.87–1.29 | general deliberation, open-capable diversity | need frontier reasoning depth |
| `intelligence` | 3 | $3.08–15 | medium-high: design tradeoffs, hard bugs, unfamiliar APIs | trivial (waste) or irreversible (use ultra) |
| `ultra` | 3 | $6–50 | HIGH-STAKES: migrations, security/auth, prod, irreversible architecture | reversible / low-complexity — premium seats burn budget |
| `mixed` | 5 | $0–1.29 | subs diversity AND a PAYG floor | tight cost budget |

**Rule of thumb:** escalate `cheap → payg → intelligence → ultra` only when the
cost of being wrong exceeds the cost of the extra completions. `ultra`'s premium
seats (fable-5 and sol-pro) are for irreversible/high-stakes work; for
medium-high complexity use `intelligence` (frontier voices without the premium
tax).
