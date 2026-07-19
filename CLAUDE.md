# fusion-local

Multi-model deliberation (5-field consensus/contradictions/coverage gaps/unique insights/
blind spots). Public repo: https://github.com/heldigard/fusion-local

**Cross-CLI**: works identically from Claude Code, Codex, Antigravity, OpenCode (console
script on `~/.local/bin`).

## What it is

The **deliberation layer** for the big model. Two modes, distinct wire contracts:

- **fusion (DEFAULT, local)**: panel of subscription workers ($0) + local-first
  cheap_llm judge (`deepseek-v4-flash` pinned T2 fallback) + `JUDGE_SCHEMA_PROMPT`.
  Cost ≈ $0–0.04.
- **fusion --openrouter**: hosted `openrouter/fusion`, every panelist searches the live
  web. PAYG, ~½ a frontier call. Default output is assistant text; `--json` is the raw
  provider Chat Completion, not the local five-field envelope.

The controller consumes and decides from the local five-field analysis. Hosted mode's
outer OpenRouter model consumes its internal Fusion analysis and returns assistant text.

## Architecture (vertical-slice package)

```
src/fusion/
├── _boundary.py     shared validation/error/scrub contracts
├── _version.py      canonical runtime version
├── config.py        constants + cross-CLI wiring (FUSION_ROUTER, cheap_llm bootstrap)
├── panel_models.py  model catalog: types, presets, MODEL_ALIASES, WORKER_GUARD (pure data)
├── panel_current.py current-controller detection + panel-seat exclusion/matching
├── panel.py         lane-1/lane-2 runners + orchestration (re-exports catalog & detection)
├── judge.py         feature: 5-field schema + cheap_llm judge synthesis
├── delegate.py     feature: legacy OpenRouter hosted fusion (--openrouter)
├── cli.py          feature: fuse() + main() + FuseOptions (parameter object)
├── capabilities.py machine-readable capability manifest (doctor/router consumer)
└── __init__.py     public API (fuse, run_panel, run_judge, FuseOptions, main, ...)
tests/
├── test_fusion.py     panel + judge + fuse + CLI (offline, mocked)
└── test_delegate.py   legacy payload/key/schema
```

Each module is one cohesive feature. Module/function names don't collide (`run_panel`,
`run_judge`).

## Cascade (panel → judge)

```
PANEL LANE 1 ($0 subs, parallel)   explicit balanced/coding/reasoning/fast/specialists profile
    fallback when < min_workers succeed ↓
PANEL LANE 2 (PAYG, HTTP direct)   deepseek-v4-pro (api.deepseek.com) · qwen3.7-max (ZenMux)
    ↓
JUDGE  cheap_complete(local-first; pinned T2=deepseek/deepseek-v4-flash) + JUDGE_SCHEMA_PROMPT
    → 5-field JSON {consensus, contradictions, coverage_gaps, unique_insights, blind_spots}
```

## Cross-CLI wiring

- `fusion-local` console script on `~/.local/bin` (PATH of every CLI) is the canonical entry.
- `fusion` shell command = installed alias → `fusion-local`.
- **lane-1** (subs) uses `FUSION_ROUTER` (default `~/.claude/scripts/codex-worker-router.py`,
  Claude ecosystem). Non-Claude CLIs: set `FUSION_ROUTER=/your/dispatch`, or `FUSION_ROUTER=`
  to disable (panel falls back to lane-2 PAYG, universal).
- **lane-1 profile**: `--subs-profile` / `FUSION_SUBS_PROFILE` selects
  `balanced`, `coding`, `reasoning`, `fast`, or `specialists`.
- **lane-1 worker modes**: `FUSION_PANEL_SUBS` (`a,b` = custom; empty = disable)
  overrides the profile. Same 3-mode semantics as `FUSION_ROUTER`.
- `--openrouter` early-delegates to `fusion.delegate.main` (legacy).

## Hardening contract (v1.3.0)

- **Judge preflight before panel spend**: `fuse()` gates on `judge.preflight()`
  (cheap_llm import + `require(CHEAP_LLM_MIN_VERSION)`) BEFORE the panel fan-out.
  `run_judge` degrades gracefully on drift or a post-panel judge transport exception,
  preserving `panel_evidence` and the structured degraded envelope.
- **Panel-side secret scrub**: `run_panel` scrubs via `cheap_llm.scrub_secrets` and
  fails closed before lane-1/lane-2 if scrubbing is unavailable.
- **Hosted fail-closed scrub**: `--openrouter` does not perform HTTP if prompt scrub is
  unavailable; key/scrub setup failures exit 1.
- **Validate before spend**: APIs use `ValueError`, CLIs use argparse exit 2; blank tasks,
  unknown presets and non-positive strict integers reach no preflight/worker/HTTP call.
- **Strict judge contract**: exact keys and types (`str` + four `list[str]`), duplicate
  keys rejected, malformed/non-dict results degraded with `panel_evidence`.
- **Safe public errors**: one line, ≤300 chars, stable metadata only; no bodies, stderr,
  exception messages, prompts, headers, invalid object reprs, or partial stdout.
- **Bounded provider responses**: panel and hosted HTTP bodies are capped at 4 MiB before
  decoding; oversized responses fail as normal operational errors.
- **Router exit-status validation**: lane-1 accepts stdout only when its dispatch process
  exits zero; partial stdout from failed dispatch is never promoted to panel evidence.
- **Router protocol**: lane-1 uses `fusion-panel-v1` (answer-only stdout, no tools,
  no router-level cloud fallback). Fusion exclusively owns PAYG fallback.
- **Final quorum**: fewer than `min_workers` successful outputs degrades before judge
  transport and preserves bounded panel evidence.
- **Judge isolation**: panel text is bounded and serialized as untrusted user data,
  never placed in the judge system message.
- **Local exit codes**: `0` = `judge_valid: true`, `2` = degraded.
- **Hosted exit codes**: `0` usable response, `1` key/scrub setup, `2` usage/operational
  failure. Hosted `--json` is raw provider JSON on success and stdout is empty on error.
- **Per-source timings**: successful and failed lane workers expose
  `duration_seconds` in source metadata, so timeout tuning uses evidence rather
  than total-panel latency guesses.
- **`--capabilities` live health**: `health.live` = `{cheap_llm_ok, cheap_llm_version,
  router_available, openrouter_key_present}` (local probes only; consumed by
  `cli-orchestration doctor`). `health.cheap_llm_min_version` is DRY from
  `judge.CHEAP_LLM_MIN_VERSION`.
  Each capability also declares invocation, inputs, prerequisites, default/JSON output
  contracts, exit codes, and recovery semantics for machine-only consumers.

## Entry points

- **Console scripts** (`pip install -e .`): `fusion-local` and `fusion`.
- **Wired-ecosystem shim**: `~/.claude/scripts/fusion-local.py` re-exports from the
  package (backward-compat for the Claude path).
- **Direct**: `python3 -m fusion.cli "<Q>"`.

## CLI

```
fusion "<Q>"                                  # local panel + judge (default)
fusion --json "<Q>"                           # full 5-field envelope as JSON
fusion --preset mixed "<Q>"                   # always subs + default PAYG panel
fusion --preset cheap "<Q>"                   # low-cost direct-provider panel
fusion --preset ultra --current-model "$MODEL" "<Q>"
fusion --preset ultra --cloud-judge --cloud-model deepseek/deepseek-v4-pro "<Q>"
fusion --cloud-model "deepseek/deepseek-v4-flash" "<Q>"
fusion --openrouter "<Q>"                     # OpenRouter hosted (web-grounded)
fusion --openrouter --json "<Q>"              # raw OpenRouter Chat Completion JSON
fusion --version
```

## Dependencies

- [`cheap-llm`](../cheap-llm) — the judge transport. Imported via `CHEAP_LLM_HOME` env
  (default `~/cheap-llm`); **no pip dependency**. `cheap_complete` provides cascade +
  secret scrub + on-disk cache.
- `codex-worker-router` (`FUSION_ROUTER`) — panel lane-1 dispatch. Optional (lane-2 is
  universal).

## Conventions

- **Vertical-slice**: feature-per-module (config/panel_models/panel_current/panel/judge/
  delegate/cli), with small shared `_boundary` and `_version` contract modules. `panel.py`
  is the execution module + facade: it re-exports `panel_models`/`panel_current` public
  names so `from fusion.panel import X` (and `panel_mod.*` in tests) is unchanged.
- `FuseOptions` dataclass — parameter object (keeps `fuse()` arity ≤ 5).
- **Secret scrub on all external paths**: judge unconditionally inside cheap_llm;
  panel and hosted delegate fail closed before external dispatch.
- **Recursion guard** on panelists: `[FUSION_PANEL][NO_DELEGATE][NO_TOOLS]`.

## Commands

- Test (offline): `python3 tests/test_fusion.py && python3 tests/test_delegate.py`
- Lint: `ruff check src/fusion/ tests/`
- Install editable: `pip install -e . --user --break-system-packages`

## Model routing

- **Panel lane 1 ($0 subs)** is profile-driven:
  - `balanced`: `claude-sonnet`, `kimic`, `zai`.
  - `coding`: `codex-spark`, `claude-sonnet`, `kimic`, `grok`.
  - `reasoning`: `claude-opus`, `codex-frontier`, `agy35-flash`, `kimic`, `zai`.
  - `fast`: `codex-quick`, `agy35-flash`, `zai`.
  - `specialists`: `kimic`, `zai`, `mimo`, `grok`.
  `grok` is the Grok Build coding seat; `mini` (M2.7) is excluded from named
  profiles because M3 supersedes it, but remains available by explicit override.
  `claude-fable` is credit-only and rejected from lane 1; use `ultra` so its
  provider and metered cost remain explicit.
- **Panel lane 2 (PAYG fallback)**: `deepseek-v4-pro` (first-party
  `api.deepseek.com` since 2026-07-17 — same weights, no OpenRouter markup),
  `qwen3.7-max` (ZenMux).
- **Cheap preset**: `deepseek-v4-flash` (DeepInfra) + `minimax-m3` (ZenMux).
  Dominated Qwen Plus and general-purpose MiMo seats are intentionally absent.
- **Intelligence preset**: `x-ai/grok-4.5`, `openai/gpt-5.6-terra`,
  `z-ai/glm-5.2` (ZenMux). Three strong, nonredundant families.
- **Ultra preset**: `claude-fable-5`, `gpt-5.6-sol-pro`, `x-ai/grok-4.5`.
  Dominated Opus/Gemini siblings are intentionally absent.
- **Judge**: local-first; `DEFAULT_JUDGE_MODEL = "deepseek/deepseek-v4-flash"`
  pins T2. `--cloud-judge` skips T1; `--cloud-model` selects that T2 model.
- **Current-model exclusion**: `--current-model` or env (`FUSION_CURRENT_MODEL`,
  `CONTROLLER_MODEL`, CLI-specific `*_MODEL`) skips matching panelists and
  reports them in `sources[]`. Claude/Codex sessions also read their canonical
  settings/config model when no env override exists.

## Preset selection by complexity

Cost is output $/M tokens (live provider catalogs, 2026-07-19). The controller decides
when to invoke fusion and which preset fits the stakes — fusion itself never
auto-invokes. Pick the cheapest panel whose downside-risk you can tolerate.

| Preset | Seats | Output $/M range | Use when | Avoid when |
|---|---|---|---|---|
| `subs` | 3–5 | $0 (subscription) | task-specific first pass; controller has subs quota left | quota exhausted or non-Claude CLI without `FUSION_ROUTER` |
| `cheap` | 2 | $0.18–1.10 | low-stakes sanity check, second opinion on routine code | irreversible / security / architecture |
| `payg` | 2 | $0.87–1.29 | general deliberation, open-capable diversity | need frontier reasoning depth |
| `intelligence` | 3 | $3.08–15 | medium-high complexity: design tradeoffs, hard bugs, unfamiliar APIs | trivial work (waste) or truly irreversible (use ultra) |
| `ultra` | 3 | $6–50 | HIGH-STAKES only: migrations, security/auth, prod deploys, irreversible architecture | anything reversible or low-complexity — premium seats burn budget for no gain |
| `mixed` | 5 | $0–1.29 | want subs diversity AND a PAYG floor | tight cost budget |

**Rule of thumb:** escalate `cheap → payg → intelligence → ultra` only when the
cost of being wrong exceeds the cost of the extra completions. `ultra`'s premium
seats (fable-5 and sol-pro) are for irreversible/high-stakes work; for
medium-high complexity use `intelligence` (frontier voices without the premium
tax).
