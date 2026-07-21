"""current-controller model detection + seat mapping."""

from __future__ import annotations

from unittest.mock import patch

from _fusion_harness import check

import fusion.panel as panel_mod


def test_detect_current_model_ignores_non_object_identity() -> None:
    with patch.dict(
        "os.environ",
        {"CLAUDE_AGENT_IDENTITY": '"not-a-dict"', "FUSION_CURRENT_MODEL": "env-model"},
        clear=True,
    ):
        model = panel_mod.detect_current_model()
    check("non-object CLAUDE_AGENT_IDENTITY falls back to env", model == "env-model", str(model))


def test_detect_current_model_ignores_non_string_identity_model() -> None:
    with patch.dict(
        "os.environ",
        {"CLAUDE_AGENT_IDENTITY": '{"model":["hostile"]}', "FUSION_CURRENT_MODEL": "env-model"},
        clear=True,
    ):
        model = panel_mod.detect_current_model()
    check("non-string identity model falls back to env", model == "env-model", str(model))


def test_detect_current_model_reads_claude_settings() -> None:
    import tempfile
    from pathlib import Path as _P

    with tempfile.TemporaryDirectory() as tmp:
        home = _P(tmp)
        settings = home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"model": "claude-fable-5[1m]"}', encoding="utf-8")
        with (
            patch.dict("os.environ", {"CLAUDECODE": "1"}, clear=True),
            patch.object(panel_mod.Path, "home", staticmethod(lambda: home)),
        ):
            model = panel_mod.detect_current_model()
    check("CLAUDECODE session reads settings.json model", model == "claude-fable-5[1m]", str(model))


def test_detect_current_model_reads_codex_settings() -> None:
    import tempfile
    from pathlib import Path as _P

    with tempfile.TemporaryDirectory() as tmp:
        home = _P(tmp)
        settings = home / ".codex" / "config.toml"
        settings.parent.mkdir(parents=True)
        settings.write_text('model = "gpt-5.6-sol"\n', encoding="utf-8")
        with (
            patch.dict("os.environ", {"CODEX_THREAD_ID": "test-session"}, clear=True),
            patch.object(panel_mod.Path, "home", staticmethod(lambda: home)),
        ):
            model = panel_mod.detect_current_model()
    check("Codex session reads config.toml model", model == "gpt-5.6-sol", str(model))


def test_detect_current_model_reads_gemini_settings() -> None:
    import tempfile
    from pathlib import Path as _P

    with tempfile.TemporaryDirectory() as tmp:
        home = _P(tmp)
        settings = home / ".gemini" / "antigravity-cli" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"model": {"name": "gemini-3.5-flash"}}', encoding="utf-8")
        with (
            patch.dict("os.environ", {"ANTIGRAVITY_AGENT": "1"}, clear=True),
            patch.object(panel_mod.Path, "home", staticmethod(lambda: home)),
        ):
            model = panel_mod.detect_current_model()
    check(
        "Antigravity session reads its own settings.json model",
        model == "gemini-3.5-flash",
        str(model),
    )


def test_detect_current_model_reads_gemini_settings_direct_string() -> None:
    import tempfile
    from pathlib import Path as _P

    with tempfile.TemporaryDirectory() as tmp:
        home = _P(tmp)
        settings = home / ".gemini" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"model": "gemini-pro-latest"}', encoding="utf-8")
        with (
            patch.dict("os.environ", {"ANTIGRAVITY_CONVERSATION_ID": "some-id"}, clear=True),
            patch.object(panel_mod.Path, "home", staticmethod(lambda: home)),
        ):
            model = panel_mod.detect_current_model()
    check("Gemini direct string model read", model == "gemini-pro-latest", str(model))


def test_subscription_mode_model_mappings_are_exact() -> None:
    cases = (
        ("codex-coding", "openai/gpt-5.6-terra"),
        ("agy3-pro", "google/gemini-3.1-pro"),
        ("agy-opus", "Claude Opus 4.6 (Thinking)"),
        ("agy-sonnet", "Claude Sonnet 4.6 (Thinking)"),
        ("agy36-flash", "Gemini 3.6 Flash (High)"),
        ("agy35-flash", "Gemini 3.5 Flash (Medium)"),
        ("qwen-cli", "qwen/qwen3.7-max"),
    )
    for worker, current_model in cases:
        check(
            f"{worker} maps to {current_model}",
            panel_mod._matches_current_model(worker, current_model),
        )
    check(
        "Antigravity Pro does not masquerade as Flash",
        not panel_mod._matches_current_model("agy3-pro", "google/gemini-3.5-flash"),
    )


def test_current_model_1m_suffix_matches_panel_seat() -> None:
    seat = ("claude-fable-5", panel_mod.OPENROUTER_URL, "anthropic/claude-fable-5", "K")
    matched = panel_mod._matches_current_model(seat, "claude-fable-5[1m]")
    check("[1m] suffix does not defeat panel de-dup", matched, str(matched))
    unrelated = ("gpt-5.6-sol-pro", panel_mod.OPENROUTER_URL, "openai/gpt-5.6-sol-pro", "K")
    check(
        "unrelated seat still allowed",
        not panel_mod._matches_current_model(unrelated, "claude-fable-5[1m]"),
    )
    check("bare fable alias matches exact seat", panel_mod._matches_current_model(seat, "fable"))
    check(
        "generic gpt family does not over-exclude sol-pro",
        not panel_mod._matches_current_model(unrelated, "gpt-5.6"),
    )
    check(
        "codex-spark matches gpt-5.6-terra",
        panel_mod._matches_current_model("codex-spark", "gpt-5.6-terra"),
    )
    check(
        "codex-spark matches gpt-5.6-terra-1m",
        panel_mod._matches_current_model("codex-spark", "gpt-5.6-terra-1m"),
    )
    check(
        "codex-spark matches terra",
        panel_mod._matches_current_model("codex-spark", "terra"),
    )
    # zai seat (z-ai/glm-5.2) and kimic seat (kimi-k2.7-code) round out the
    # subscription panel; their exclusion aliases were added but not exercised.
    check(
        "zai matches glm-5.2",
        panel_mod._matches_current_model("zai", "glm-5.2"),
    )
    check(
        "zai matches glm-5.2[1m] context suffix",
        panel_mod._matches_current_model("zai", "glm-5.2[1m]"),
    )
    check(
        "kimic matches kimi-k2.7-code",
        panel_mod._matches_current_model("kimic", "kimi-k2.7-code"),
    )
    check(
        "unrelated glm does not over-exclude zai seat for non-glm current",
        not panel_mod._matches_current_model("codex-spark", "glm-5.2"),
    )


TESTS = [
    (
        "test_detect_current_model_ignores_non_object_identity",
        test_detect_current_model_ignores_non_object_identity,
    ),
    (
        "test_detect_current_model_ignores_non_string_identity_model",
        test_detect_current_model_ignores_non_string_identity_model,
    ),
    (
        "test_detect_current_model_reads_claude_settings",
        test_detect_current_model_reads_claude_settings,
    ),
    (
        "test_detect_current_model_reads_codex_settings",
        test_detect_current_model_reads_codex_settings,
    ),
    (
        "test_detect_current_model_reads_gemini_settings",
        test_detect_current_model_reads_gemini_settings,
    ),
    (
        "test_detect_current_model_reads_gemini_settings_direct_string",
        test_detect_current_model_reads_gemini_settings_direct_string,
    ),
    (
        "test_subscription_mode_model_mappings_are_exact",
        test_subscription_mode_model_mappings_are_exact,
    ),
    (
        "test_current_model_1m_suffix_matches_panel_seat",
        test_current_model_1m_suffix_matches_panel_seat,
    ),
]
