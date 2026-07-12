---
title: "fix: Harden deliberation failure boundaries"
type: fix
status: completed
date: 2026-07-12
---

# fix: Harden deliberation failure boundaries

## Enhancement Summary

**Deepened on:** 2026-07-12
**Sections enhanced:** proposed solution, technical considerations, acceptance criteria,
and validation.
**Research applied:** repository/spec-flow analysis, `python-pro` error-handling/testing,
and cross-cutting software-development review.

### Key Improvements

1. Fix the recovery shape at five fields plus the judge metadata already documented by
   `run_judge`: `judge_model`, `judge_valid`, `cost`, and `latency`.
2. Normalize new boundary errors to one line and at most 300 characters; never promote
   failed router stdout into either evidence or source errors.
3. Test the behavior at unit, orchestration, and CLI boundaries, and register every new
   test in the project's manual `TESTS` runner as well as pytest discovery.

### New Considerations Discovered

- Catching `Exception` only around `cheap_complete` intentionally leaves
  `KeyboardInterrupt` and `SystemExit` untouched and avoids promising recovery from
  unrelated programming defects elsewhere in `run_judge`.
- The requested judge model is useful configuration metadata on failure, but
  `judge_valid=False` must make clear that no valid provider response was observed.

## Overview

Make two existing reliability contracts true at their external-process boundaries:

1. A runtime/transport exception from the economical judge must degrade to the normal
   five-field envelope and preserve the panel signal instead of crashing the CLI.
2. A subscription router process that exits non-zero must be reported as a failed
   panelist even when it wrote partial stdout.

The change stays inside the local panel/judge pipeline. It does not alter model presets,
network endpoints, the public package name, or the legacy `--openrouter` response format.

## Problem Statement / Motivation

The project documents graceful degradation after panel spend, but
`cheap_llm.cheap_complete(...)` is currently an unguarded call in
`src/fusion/judge.py:121`. A transport/runtime exception propagates through
`run_judge -> fuse -> main`, so callers receive neither the five Fusion fields nor
`panel_evidence`, and the CLI cannot honor its documented degraded exit code `2`.

Separately, `src/fusion/panel.py:297` considers any non-empty router stdout a success
without checking `CompletedProcess.returncode`. A failed router can therefore inject
partial/error output into the judge as if it were valid panel evidence.

Baseline evidence:

- `pytest -q`: 40 passed.
- `ruff check src/fusion tests`: clean.
- `codescan all`: zero secrets, SAST, dead-code, lint, type, or architecture findings
  (architecture sensor skipped because no dependency-cruiser config applies).
- Offline reproduction of a judge `TimeoutError` currently propagates uncaught.

## Proposed Solution

### Judge transport exception isolation

- Wrap only the `cheap_complete` invocation with `except Exception`; do not catch
  `KeyboardInterrupt`, `SystemExit`, or other `BaseException` subclasses.
- Return `empty_fields(...)` with `judge_valid=False`, the requested judge model, a
  single-line actionable error capped at 300 characters, `cost=0`, `latency=0`, and
  `_panel_evidence(panel_results)`.
- Keep `consensus` as a stable recovery instruction rather than copying exception or
  panel text into it.
- Preserve all existing behavior for an empty panel, failed preflight, invalid JSON,
  and schema-invalid JSON.

### Subscription router exit correctness

- Check `proc.returncode` before accepting stdout.
- On non-zero exit, return the normal failed-source shape with a bounded stderr detail
  when available. The return code takes precedence over any stdout, which is not copied
  into evidence or error metadata.
- Preserve the existing timeout, missing-router, empty-output, and exception paths.

### Tests and documentation

- Add unit coverage for a thrown judge transport exception.
- Add `fuse`/CLI coverage proving the degraded envelope remains parseable, sources and
  panel evidence survive, and the CLI returns `2` rather than raising.
- Add subprocess coverage for non-zero exit with non-empty stdout.
- Update `README.md` and `CLAUDE.md` so the hardening contract explicitly includes
  post-panel judge exceptions and router exit-status validation.

## Technical Considerations

- **Architecture:** no new module or dependency; the feature-per-module layout remains
  intact.
- **Cost:** preflight still executes before fan-out. The new judge branch runs only
  after a panel has already completed and exists to recover its signal.
- **Security/privacy:** error text must be bounded; panel output remains only in the
  existing truncated `panel_evidence` projection. Failed router stdout is not promoted
  into evidence. New exception/stderr details are flattened to one line and capped at
  300 characters; normalization of older error branches remains out of scope.
- **Compatibility:** the five semantic fields, source metadata, public exports, and
  success/degraded exit codes remain unchanged.

## System-Wide Impact

- **Interaction graph:** `main -> fuse -> run_panel -> run_judge -> cheap_complete`.
  The new judge branch returns to `fuse`, which still attaches `sources`, `preset`, and
  `total_latency`; `main` then prints the envelope and returns `2`.
- **Error propagation:** worker subprocess failures remain isolated in `_run_lane`;
  judge exceptions become data in the degraded envelope instead of process failures.
- **State lifecycle:** the project is read-only apart from external model calls and the
  judge cache owned by `cheap_llm`; no persistent project state is introduced.
- **API surface parity:** direct `run_judge`, public `fuse`, JSON CLI, and readable CLI
  share the same recovery branch. The hosted legacy delegate is explicitly out of scope.
- **Integration scenarios:** successful panel plus judge exception; non-zero router with
  partial stdout; unchanged valid judge response; unchanged invalid-JSON response.

## Acceptance Criteria

- [x] An `Exception` raised by `cheap_complete` does not propagate; `KeyboardInterrupt`
      and `SystemExit` remain uncaught.
- [x] The recovery result contains all five Fusion fields, `judge_valid=False`, an
      actionable single-line error of at most 300 characters, the requested judge model,
      `cost=0`, `latency=0`, and preserved panel evidence.
- [x] Recovery `consensus` contains neither exception detail nor panel output.
- [x] `fuse` retains `sources`, `preset`, and `total_latency` on that recovery path.
- [x] JSON CLI stdout contains only a parseable envelope and returns exit code `2` for
      that recovery path, without traceback noise.
- [x] A non-zero router exit is a failed source even when stdout is non-empty.
- [x] The router error reports its status, caps normalized stderr at 300 characters, and
      never contains partial stdout; zero exit with non-empty stdout remains successful.
- [x] Existing valid/invalid judge behavior and panel fallbacks remain green.
- [x] `pytest -q`, `python3 tests/test_fusion.py`, `python3 tests/test_delegate.py`,
      `ruff check src/fusion tests`, `python3 -m compileall -q src tests`,
      `git diff --check`, and `codescan all -p . --summary-only --json --fail-on never`
      pass with no new findings.
- [x] README and internal project guidance describe the corrected behavior.

## Success Metrics

- Zero uncaught traceback for simulated `cheap_complete` transport failure.
- Zero false-success panel result for simulated non-zero router exit.
- No regression in the baseline test and static-analysis suites.

## Dependencies & Risks

- `cheap_llm >= 1.1.1` remains the versioned judge contract.
- Exception messages may contain provider-specific text; cap what is surfaced.
- Reporting the requested judge model does not prove the provider completed a call; the
  result remains explicitly invalid.
- Live paid/provider smoke tests are unnecessary for deterministic boundary behavior and
  are excluded to avoid cost and credential use.

## Deferred Opportunities

- Decide whether the legacy `--openrouter` mode should be normalized into the same JSON
  envelope or documented as structured prose/raw-provider JSON.
- Define programmatic validation policy for invalid presets, non-positive timeouts, and
  `min_workers <= 0` before changing those public API semantics.
- Consider a single-source version fallback instead of the current source-run `1.0.0`
  fallback in `fusion.__init__` and `fusion.cli`.

## Post-Deploy Monitoring & Validation

- **Search terms:** `judge transport error`, `router exited with status`, and unexpected
  Python tracebacks from `fusion-local`.
- **Expected healthy signals:** valid judge calls still return exit `0`; simulated or real
  judge transport failures return a parseable envelope with exit `2`; failed routers
  appear as failed `sources[]` entries without partial stdout.
- **Failure/rollback trigger:** revert this change if valid judge responses begin
  degrading or zero-exit router responses are rejected.
- **Validation window and owner:** inspect the next 10 local invocations after rollout;
  owner is the operator updating the editable `fusion-local` install.

## Sources & References

- Judge boundary: `src/fusion/judge.py:84` and `src/fusion/judge.py:121`.
- CLI orchestration and exit contract: `src/fusion/cli.py:41` and
  `src/fusion/cli.py:180`.
- Router boundary: `src/fusion/panel.py:263`.
- Existing neighboring regressions: `tests/test_fusion.py:276`,
  `tests/test_fusion.py:312`, `tests/test_fusion.py:600`, and
  `tests/test_fusion.py:689`.
- Project decisions: `.memory-bank/systemPatterns.md` (preflight before spend,
  evidence preservation, thin deliberation hand).
