---
title: "fix: Complete contract safety hardening"
type: fix
status: active
date: 2026-07-12
---

# fix: Complete contract safety hardening

## Enhancement Summary

**Deepened on:** 2026-07-12  
**Sections enhanced:** validation ownership, external errors, judge schema, hosted output,
version imports, capabilities, and test strategy.  
**Research applied:** repository archaeology, SpecFlow, `python-pro`,
`software-development`, and current official OpenRouter Fusion documentation.

### Key refinements

1. Public errors use only stable safe metadata (operation, exception class, HTTP status,
   return code). Provider bodies, stderr, exception messages, prompts, headers, and
   returned object representations are never exposed merely because they are truncated.
2. Hosted success accepts exactly a non-empty string at
   `choices[0].message.content`; unfamiliar content-part shapes are rejected rather than
   guessed or concatenated.
3. Validation ownership is explicit per public entry, including `opts`, `panel_results`,
   `current_model`, and `cloud_model`, and happens before preflight or any side effect.
4. All validation and transport tests are offline; live hosted smoke remains a separate
   authority boundary and is not part of completion.

## Overview

Finish the repository review by hardening every public execution boundary that can
dispatch paid/external work, validating model output contracts without coercion, making
hosted OpenRouter behavior truthful and failure-safe, and removing duplicated runtime
version resolution.

This plan builds on the completed failure-boundary work in
`docs/plans/2026-07-12-001-fix-failure-boundary-hardening-plan.md`. Existing uncommitted
changes are preserved and extended; no live paid calls or credential reads are required.

## Research Summary

### Local findings

- `run_panel(preset="unknown")` currently falls through to `PANEL_PAYG`, creating an
  unexpected-spend path for the public Python API.
- Non-positive timeouts, `min_workers`, and hosted `max_tokens` pass through until lower
  layers fail or change fallback behavior.
- `mixed` is currently equivalent to `subs` when enough subscription workers succeed,
  contradicting its documented “subs + PAYG augmentation” meaning.
- A non-dict `cheap_complete` result still raises after the new transport-exception
  boundary; `_run_lane` can also abort if a runner returns a non-dict.
- Judge schema validation checks only key presence and silently coerces wrong types.
- The hosted delegate has unhandled timeout/JSON-malformed paths, unbounded provider
  errors, no prompt scrub, and reports malformed 2xx responses as success.
- Runtime version lookup is duplicated in `fusion.__init__` and `fusion.cli`, with a stale
  source fallback (`1.0.0` versus distribution `1.2.0`).

### Official OpenRouter contract

OpenRouter's current Fusion documentation confirms that `openrouter/fusion` returns the
outer assistant response through `choices[0].message.content`; the internal judge emits
structured analysis to that outer model. Therefore the legacy delegate must not claim
the local `fusion-envelope-v1` wire contract. Its default output remains assistant text,
and `--json` remains the raw OpenRouter Chat Completion response.

Sources:

- https://openrouter.ai/docs/guides/features/plugins/fusion.md
- https://openrouter.ai/docs/guides/routing/routers/fusion-router.md

## Proposed Solution

### 1. Shared boundary safety

Add one small internal boundary module for:

- a single public-error length (300 characters);
- whitespace-flattened, bounded error formatting from trusted metadata only;
- strict positive-integer parsing/validation (`bool` is not an integer input);
- non-empty string validation;
- secret scrubbing with explicit best-effort or fail-closed policy.

Keep canonical version resolution in a separate stdlib-only `_version.py` module so the
boundary module remains cohesive.

Panel direct use retains best-effort scrub for backwards compatibility. The hosted
delegate uses fail-closed scrub because it otherwise sends the prompt directly to a
third-party API without the local `fuse()` preflight.

### 2. Validate before dispatch

- Define one `PANEL_PRESETS` tuple in the panel feature and reuse it from CLI and
  capabilities.
- Validate each entry's owned arguments before preflight or side effects:
  - `fuse`: non-empty string task, `FuseOptions` instance, known preset, positive strict
    integer timeouts/min-workers, optional non-empty judge/current model strings;
  - `run_panel`: non-empty string task, known preset, positive strict integer timeout and
    min-workers, optional non-empty current-model string;
  - `run_judge`: non-empty string task, `list[dict]` panel results, positive strict
    integer timeout, optional non-empty cloud-model string.
- Python APIs raise deterministic `ValueError`; both CLIs use a positive-int argparse
  type and exit 2 for invalid usage.
- Do not invent upper bounds: require integer values strictly greater than zero.
- Treat empty judge-model strings as invalid when a model string is provided.

### 3. Correct panel semantics and isolation

- `preset="mixed"` always executes the subscription lane and the default PAYG lane,
  while preserving current-model exclusion in both.
- Unknown presets never fall back to PAYG.
- `_run_lane` converts non-dict runner returns into a normal failed source with duration
  instead of raising; valid workers continue.
- `_http_worker` treats non-string assistant content as a malformed response.
- Apply the shared bounded-error policy to every panel error exposed through
  `sources[]`; never include failed partial stdout, stderr, response bodies, exception
  messages, or invalid runner representations.

### 4. Enforce the judge wire contract

- A non-dict transport result becomes a degraded five-field envelope with preserved
  `panel_evidence`.
- Valid judge JSON must have exactly `FUSION_FIELDS`, with `consensus: str` and the four
  remaining fields as `list[str]`. Empty lists remain valid.
- Reject missing/extra keys, wrong container types, non-string list items, and non-string
  consensus. Reject duplicate JSON object keys and remove silent coercion.
- Replace provider-reported judge error text with stable local error codes/messages;
  provider text never enters the public envelope.

### 5. Harden the hosted delegate without changing its wire format

- Keep early `--openrouter` delegation and existing payload configuration.
- Scrub the prompt before constructing messages; scrub failure is a local configuration
  failure (exit 1), with no HTTP call and no underlying exception detail.
- Preserve exit codes: `0` usable response, `1` missing key/scrub configuration,
  `2` invalid CLI usage or operational/provider/malformed-response failure.
- Catch HTTP, network, timeout/OSError, read, and JSON-decode failures; emit one bounded
  stderr line from safe metadata and no traceback. `_call` raises one internal typed
  failure; only `main` maps failures to stderr/exit codes.
- Treat a 2xx provider `error` object or missing/non-usable assistant content as failure.
- Default success stdout is only a non-empty string from
  `choices[0].message.content`. `--json` success stdout is only the raw provider response.
  Error stdout stays empty. Content arrays/objects are malformed rather than inferred.
- Add hosted `--version` and document the distinct output contract.
- Preserve delegated `--help`/`--version` without prompt, key, scrub, or HTTP;
  `--openrouter --capabilities` remains invalid usage with exit 2.

### 6. Canonical version and capability metadata

- Resolve `fusion-local` distribution metadata once in a stdlib-only internal version
  module, catching only `PackageNotFoundError`.
- Use honest `0+unknown` when metadata is unavailable rather than a stale release value.
- Reuse the canonical value from package exports, local CLI, hosted delegate, and
  capabilities.
- Make capabilities derive its version and presets rather than accepting divergent
  injection. Describe per-command default/JSON output contracts; raw hosted JSON is not
  labeled as `fusion-envelope-v1` merely because it is valid JSON.

## System-Wide Impact

- **Local flow:** `main -> validation -> fuse -> preflight -> panel -> judge`.
  Invalid input exits before any external action.
- **Hosted flow:** `main --openrouter -> delegate validation -> key -> scrub -> HTTP ->
  response validation -> text/raw JSON`.
- **Error propagation:** public Python input errors are `ValueError`; runtime model errors
  become failed sources/degraded envelopes; hosted CLI errors become bounded stderr plus
  exit 1/2.
- **Cost lifecycle:** invalid input cannot create pool, subprocess, HTTP, or judge spend;
  explicit `mixed` intentionally incurs both lanes.
- **Compatibility:** local valid output shape is unchanged. Previously coerced malformed
  judge JSON becomes correctly degraded. Hosted output stays text/raw JSON and is now
  documented instead of being mislabeled as the local envelope.

## Acceptance Criteria

- [ ] Invalid task/preset/numeric inputs fail before any external dispatch.
- [ ] API entry points raise `ValueError`; CLI entry points use argparse exit 2.
- [ ] `FuseOptions`, `panel_results`, model-string options, strict integers, and bool
      edge cases follow the documented validation matrix.
- [ ] `mixed` dispatches subscription and PAYG lanes even when subscription workers meet
      `min_workers`, while current-model exclusions remain effective.
- [ ] Non-dict worker returns become failed sources; other workers complete.
- [ ] Non-dict judge results and malformed strict schemas degrade with evidence, never
      traceback or coercion.
- [ ] All public panel/judge/delegate errors are single-line and at most 300 characters.
- [ ] Public errors never contain injected secret markers from exception messages,
      stderr, provider bodies, prompts, headers, or malformed return representations.
- [ ] Hosted prompts are scrubbed before HTTP; missing key or scrub failure makes zero
      network calls.
- [ ] Hosted HTTP/network/timeout/invalid JSON/provider-error/malformed-success paths
      return exit 2, bounded stderr, empty stdout, and no traceback.
- [ ] Hosted success returns only assistant text or raw provider JSON according to flag.
- [ ] Package, both CLIs, and capabilities report the same canonical version.
- [ ] Capabilities reuse panel presets and distinguish local envelope from hosted output.
- [ ] README and CLAUDE document costs, output formats, validation, and exit codes truthfully.
- [ ] New tests are registered in both pytest discovery and manual runners.
- [ ] `pytest -q`, both manual runners, Ruff, compileall, `git diff --check`, CLI smoke
      checks, and `codescan all` pass with no findings.

## Risks and Mitigations

- **Behavior tightening:** callers relying on invalid presets or malformed judge coercion
  will now fail/degrade. This is intentional because the old behavior could spend money
  or mark invalid data as valid.
- **Mixed cost increase:** only explicit `mixed` calls change; documentation and tests
  make the cost semantics unambiguous.
- **Hosted scrub dependency:** canonical local operation already depends on `cheap_llm`;
  fail-closed hosted behavior prevents accidental secret disclosure.
- **Provider variation:** content validation may support string and standard text-part
  responses in the future, but this change accepts only the official string content
  shape and rejects unknown shapes rather than guessing.
- **No paid smoke:** transport behavior is deterministically covered with mocked HTTP;
  credentials and live spend stay out of scope.

## Validation Commands

```bash
pytest -q
python3 tests/test_fusion.py
python3 tests/test_delegate.py
ruff check src/fusion tests
python3 -m compileall -q src tests
python3 -m fusion.cli --capabilities | python3 -m json.tool >/dev/null
git diff --check
codescan all -p . --summary-only --json --fail-on never
```

## Post-Deploy Monitoring & Validation

- No automatic live/paid monitoring is required: this local CLI has no telemetry or
  deployment service, and adding one would be out of scope.
- Offline release validation checks stable error prefixes, clean JSON stdout, absence of
  tracebacks/secret markers, and zero mocked dispatch for invalid input.
- Any future hosted smoke is a separate explicitly authorized action using a test prompt;
  it is not part of this plan's completion criteria.
