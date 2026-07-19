#!/usr/bin/env python3
"""Standalone regression gate for the ``fusion`` package.

Aggregates the per-domain slice modules (panel/judge/fuse/cli/cworker) and runs
the shared deterministic check() harness, preserving the legacy
``python3 tests/test_fusion.py`` contract. pytest collects each slice directly;
this module only wires the standalone runner.
"""

from __future__ import annotations

from _fusion_harness import main_from
from test_fusion_cli import TESTS as _cli
from test_fusion_cworker import TESTS as _cworker
from test_fusion_fuse import TESTS as _fuse
from test_fusion_judge import TESTS as _judge
from test_fusion_panel import TESTS as _panel
from test_fusion_panel_detection import TESTS as _detection

TESTS = _panel + _detection + _judge + _fuse + _cli + _cworker


def main() -> int:
    return main_from(TESTS)


if __name__ == "__main__":
    raise SystemExit(main())
