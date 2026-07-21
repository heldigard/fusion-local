# Changelog

All notable changes to fusion-local are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/), adheres to
[Semantic Versioning](https://semver.org/).

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
