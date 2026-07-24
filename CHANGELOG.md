# Changelog

All notable changes to fusion-local are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/), adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- `run_panel` default `timeout` aligned to 120s (was 60). The v1.4.0 tier-aware
  timeout work raised the CLI/`FuseOptions` default but left the public API
  default at the value that starved reasoning seats; direct `run_panel`
  callers now get the same budget as the CLI.
- Subs-profile resolution (`custom` override, explicit profile, package
  default) is now shared by `fuse()` and `run_panel` through
  `panel.invocation_subs_profile` instead of being duplicated in both.

### Fixed
- README model-routing roster synced with the catalog: `reasoning`/`fast`
  profiles list Gemini 3.6 Flash (`agy36-flash`, renamed in 1.4.x docs drift)
  and `specialists` includes the Qwen Coding Plan (`qwenc`) seat.
- README/CLAUDE.md test layout and commands reflect the per-domain test
  slices; `pytest` documented as the primary offline gate.

## [1.5.0] - 2026-07-22

### Added
- `--allow-payg-fallback` and `FuseOptions.allow_payg_fallback` make PAYG
  escalation from the default subscription preset invocation-scoped and
  auditable.

### Changed
- The default `subs` preset no longer enters the lane-2 panel or T2 judge after
  a quorum/local failure unless that invocation opts in. Explicit metered
  presets continue to authorize their own panel and judge routes.
- Judge scales with the panel preset: `ultra`/`intelligence` now default to the
  strong cloud judge `deepseek/deepseek-v4-pro` (cloud-only, `prefer_local=False`),
  since a 4B local judge cannot faithfully synthesize frontier panel output.
  Cheaper presets keep the local-first `deepseek/deepseek-v4-flash` judge.
  `FuseOptions.cloud_model`/`judge_prefer_local` now default to `None` (= scale
  by preset). Explicit option values override inference; `--cloud-judge` forces
  cloud-only on local-first presets and `--cloud-model` pins a different T2.
- Default `judge_timeout` raised 30s -> 45s (`FuseOptions`, `--judge-timeout`,
  `run_judge`). The budget now covers a cold T1 local load (~25s,
  `cheap_llm` `LOCAL_COLD_TIMEOUT`) plus a full T2 cloud attempt (~18s); the
  prior 30s starved T2 after a cold local miss and failed the judge even when
  the panel had succeeded.

## [1.4.0] - 2026-07-20

### Changed
- Default per-panelist `panel_timeout` raised 60s -> 120s. Reasoning-tier seats
  (Opus/Kimi/GLM/Grok/Sol/Terra/Pro) legitimately run 60-120s; the prior flat 60s
  cap starved them and dropped quorum (2026-07-20 incident: `reasoning` subs
  profile where only the flash seat responded while Opus/Kimi/GLM timed out).
  `panel(120) + judge(30) = 150s` stays under the delegate overall budget (180s).

### Added
- Tier-aware per-seat timeout: fast-tier seats (`flash/haiku/lite/luna/quick/mini/
  mimo/v4-flash`) are internally capped at `FAST_SEAT_TIMEOUT=60` so a hung
  flash/haiku worker fails fast; reasoning seats get the full `panel_timeout`.
- `panel_quorum.seats[]` per-seat status `{source, lane, outcome}` in the fuse
  envelope, so consumers can distinguish a timeout wall from genuine model
  disagreement on quorum loss. `outcome` is one of `responded`, `timed_out`,
  `missing_key`, `skipped`, `failed`, `empty`.

### Fixed
- `test_fuse_requires_final_panel_quorum` updated to assert the enriched
  `panel_quorum` envelope (now carries `seats`).

### Notes
- `panel.py` carries a `vs-soft-allow` marker (matching `cli.py`): `run_panel` is a
  single cohesive orchestration pipeline whose parameter count and mixed-preset
  concurrent-lane nesting are intrinsic to one responsibility, not mixed concerns.

## [1.3.1] - prior

- See git history.
