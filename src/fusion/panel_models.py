"""Panel model catalog — types, presets, aliases, and the worker guard prompt.

Pure data: this module changes when the model roster, cost-tier presets, or
alias map changes — independent of how workers execute (``panel``) or how the
current controller model is detected (``panel_current``). Consumed by both.
"""

from __future__ import annotations

from typing import TypeVar

# Lane-2 entry shape: (alias, url, model_name, api_key_env).
Spec = tuple[str, str, str, str]
Worker = str | Spec
LaneWorker = TypeVar("LaneWorker", str, Spec)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"

DEEPINFRA_URL = "https://api.deepinfra.com/v1/openai/chat/completions"
DEEPINFRA_KEY_ENV = "DEEPINFRA_API_KEY"

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_KEY_ENV = "DEEPSEEK_API_KEY"

ZENMUX_URL = "https://zenmux.ai/api/v1/chat/completions"
ZENMUX_KEY_ENV = "ZENMUX_API_KEY"

# Alibaba Cloud Model Studio — Qwen Coding Plan (Token Plan Singapore). First-party
# subscription endpoint; cheaper than ZenMux for the same weights. The router
# (``FUSION_ROUTER``/cli-orchestration) launches the ``qwenc`` Claude Code wrapper
# as a lane-1 seat; this constant is reserved for future first-party direct calls.
QWEN_ALIYUN_URL = (
    "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
)
QWEN_API_KEY_ENV = "QWEN_API_KEY"

HTTP_REFERER = "https://github.com/heldigard/fusion-local"
HTTP_TITLE = "fusion-local"

# Lane 1: $0 subscription workers, grouped by task rather than running every
# available seat on every deliberation.  The controller selects the profile;
# Fusion never infers task type or silently changes model families.
SUBS_PROFILE_DEFAULT = "balanced"
# These cworker modes are metered through usage credits, not covered by the
# ordinary Claude subscription allocation. They must use an explicit PAYG
# preset so Fusion can report the provider and cost honestly.
CREDIT_ONLY_WORKERS: frozenset[str] = frozenset({"claude-fable"})

SUBS_PROFILES: dict[str, tuple[str, ...]] = {
    # Three live-verified, orthogonal families keep judge input bounded. Claude
    # avoids echoing the default Codex controller while Kimi and GLM add strong
    # open-model perspectives.
    "balanced": ("claude-sonnet", "kimic", "zai"),
    # Patch/coding hands: Terra for economical implementation, Kimi/Grok for
    # code specialization, and Sonnet as the independent reviewer.
    "coding": ("codex-spark", "claude-sonnet", "kimic", "grok"),
    # Architecture and difficult reasoning. Opus stays inside the Claude
    # subscription; credit-only Fable is reserved for the explicit ultra tier.
    "reasoning": ("claude-opus", "codex-frontier", "agy36-flash", "kimic", "zai"),
    # High-volume triage where latency and subscription conservation dominate.
    "fast": ("codex-quick", "agy36-flash", "zai"),
    # Specialist diversity.  MiniMax M2.7 is intentionally absent because M3
    # supersedes it; the legacy ``mini`` seat remains available only by an
    # explicit FUSION_PANEL_SUBS override.
    "specialists": ("kimic", "zai", "mimo", "grok", "qwenc"),
}
SUBS_PROFILE_NAMES: tuple[str, ...] = tuple(SUBS_PROFILES)

# Backward-compatible name consumed by capability metadata and callers that
# inspect the nominal default panel.
PANEL_SUBS: list[str] = list(SUBS_PROFILES[SUBS_PROFILE_DEFAULT])

# Cross-CLI override for lane-1 (mirrors FUSION_ROUTER semantics):
# unset → PANEL_SUBS default; "" → disable lane-1; "a,b" → custom worker modes.
PANEL_SUBS_ENV = "FUSION_PANEL_SUBS"
PANEL_SUBS_PROFILE_ENV = "FUSION_SUBS_PROFILE"

# Lane 2: PAYG fallback (HTTP direct) — universal cross-CLI. deepseek-v4-pro is
# first-party api.deepseek.com (same weights, no aggregator markup); other seats
# bind explicitly to ZenMux, DeepInfra, or OpenRouter. Presets are explicit so the controller
# can pick cost vs depth intentionally. Cost tiers (output $/M):
#   cheap        ~$0.18-1.10  — economical open models
#   payg         ~$0.87-1.29  — open capable (default deliberation)
#   intelligence ~$3.08-15    — frontier-accessible, NO premium $25-50/M seats
#   ultra        ~$6-50       — full frontier incl. premium closed (fable/sol-pro)
PANEL_PAYG: list[tuple[str, str, str, str]] = [
    ("deepseek-v4-pro", DEEPSEEK_URL, "deepseek-v4-pro", DEEPSEEK_KEY_ENV),
    # Same Qwen weights at a materially lower live catalog price than
    # OpenRouter; provider/model binding is explicit to avoid slug guessing.
    ("qwen3.7-max-zm", ZENMUX_URL, "qwen/qwen3.7-max", ZENMUX_KEY_ENV),
]

PANEL_CHEAP: list[tuple[str, str, str, str]] = [
    ("deepseek-v4-flash-di", DEEPINFRA_URL, "deepseek-ai/DeepSeek-V4-Flash", DEEPINFRA_KEY_ENV),
    ("minimax-m3-zm", ZENMUX_URL, "minimax/minimax-m3", ZENMUX_KEY_ENV),
]

PANEL_ULTRA: list[tuple[str, str, str, str]] = [
    ("claude-fable-5", OPENROUTER_URL, "anthropic/claude-fable-5", OPENROUTER_KEY_ENV),
    ("gpt-5.6-sol-pro", OPENROUTER_URL, "openai/gpt-5.6-sol-pro", OPENROUTER_KEY_ENV),
    ("grok-4.5", OPENROUTER_URL, "x-ai/grok-4.5", OPENROUTER_KEY_ENV),
]

# Intelligence: three frontier-accessible families for medium-high complexity.
# GLM 5.2 replaces weaker DeepSeek/Gemini seats; premium Fable/Sol-Pro remain
# exclusive to ultra.
PANEL_INTELLIGENCE: list[tuple[str, str, str, str]] = [
    ("grok-4.5", OPENROUTER_URL, "x-ai/grok-4.5", OPENROUTER_KEY_ENV),
    ("gpt-5.6-terra", OPENROUTER_URL, "openai/gpt-5.6-terra", OPENROUTER_KEY_ENV),
    ("glm-5.2-zm", ZENMUX_URL, "z-ai/glm-5.2", ZENMUX_KEY_ENV),
]

PAYG_PRESETS: dict[str, list[Spec]] = {
    "payg": PANEL_PAYG,
    "cheap": PANEL_CHEAP,
    "intelligence": PANEL_INTELLIGENCE,
    "ultra": PANEL_ULTRA,
}

PANEL_PRESETS: tuple[str, ...] = ("subs", "payg", "cheap", "intelligence", "ultra", "mixed")

# Subscription worker -> (display model, provider model) for current-model
# matching. Lane-1 modes are opaque strings; this table is how a subscription
# seat is compared against the controller's own model id.
SUBS_WORKER_MODELS: dict[str, tuple[str, ...]] = {
    "codex-quick": ("gpt-5.6-luna", "openai/gpt-5.6-luna"),
    "codex-spark": ("gpt-5.6-terra", "openai/gpt-5.6-terra"),
    "codex-coding": ("gpt-5.6-terra", "openai/gpt-5.6-terra"),
    "codex-research": ("gpt-5.6-terra", "openai/gpt-5.6-terra"),
    "codex-frontier": ("gpt-5.6-sol", "openai/gpt-5.6-sol"),
    "codex-deep": ("gpt-5.6-sol", "openai/gpt-5.6-sol"),
    "claude-sonnet": ("claude-sonnet-5", "anthropic/claude-sonnet-5"),
    "claude-opus": ("claude-opus-4.8", "anthropic/claude-opus-4.8"),
    "agy36-flash": ("gemini-3.6-flash", "google/gemini-3.6-flash", "Gemini 3.6 Flash (High)"),
    "agy35-flash": ("gemini-3.6-flash", "google/gemini-3.6-flash", "gemini-3.5-flash", "Gemini 3.5 Flash (Medium)"),
    # These mappings follow the exact inventory reported by ``agy models``.
    "agy3-pro": (
        "gemini-3.1-pro",
        "google/gemini-3.1-pro",
    ),
    "agy-opus": (
        "claude-opus-4.6",
        "anthropic/claude-opus-4.6",
        "Claude Opus 4.6 (Thinking)",
    ),
    "agy-sonnet": (
        "claude-sonnet-4.6",
        "anthropic/claude-sonnet-4.6",
        "Claude Sonnet 4.6 (Thinking)",
    ),
    # All K3 + K2.7 id forms so the seat is excluded when the controller itself
    # runs Kimi (Claude wrapper id ``kimi-k3``/``kimi-3`` or native ``k3``) —
    # prevents an echo-chamber where a K3 brain "second-opinions" a K3 worker.
    "kimic": (
        "kimi-k3",
        "moonshotai/kimi-k3",
        "k3",
        "kimi-3",
        "kimi-code/k3",
        "kimi-k2.7-code",
        "moonshotai/kimi-k2.7-code",
    ),
    "zai": ("glm-5.2", "z-ai/glm-5.2"),
    "mini": ("minimax-m2.7", "minimax/minimax-m2.7"),
    "mimo": ("mimo-v2.5-pro", "xiaomi/mimo-v2.5-pro"),
    # Alibaba Qwen Coding Plan (Token Plan Singapore) — top preview qwen3.8-max-preview
    # plus stable qwen3.7-max and qwen3.7-plus spellings. Excluded when the controller
    # itself runs a Coding Plan model so the seat cannot echo-chamber the brain.
    "qwenc": (
        "qwen3.8-max-preview",
        "qwen/qwen3.8-max-preview",
        "qwen3.7-max",
        "qwen/qwen3.7-max",
        "Qwen/Qwen3.8-Max-Preview",
    ),
    "qwen-cli": ("qwen3.7-max", "qwen/qwen3.7-max"),
    # Grok Build CLI is a coding seat.  Keep the 4.5 aliases as compatibility
    # spellings because the subscription service may report the backing model.
    "grok": (
        "grok-build-0.1",
        "x-ai/grok-build-0.1",
        "grok-4.5",
        "x-ai/grok-4.5",
    ),
}

# Alias fan-out for current-model matching: a controller model id may appear
# under several spellings; all of them must match the panel seat.
MODEL_ALIASES: dict[str, tuple[str, ...]] = {
    "~google/gemini-pro-latest": (
        "google/gemini-pro-latest",
        "gemini-pro-latest",
        "gemini-3.5-pro",
        "google/gemini-3.5-pro",
    ),
    "anthropic/claude-opus-4.8": ("claude-opus-4-8", "claude-opus-4.8", "opus"),
    "anthropic/claude-opus-4.6": (
        "claude-opus-4-6",
        "claude-opus-4.6",
        "Claude Opus 4.6 (Thinking)",
    ),
    "anthropic/claude-sonnet-5": ("claude-sonnet-5", "sonnet"),
    "anthropic/claude-sonnet-4.6": (
        "claude-sonnet-4-6",
        "claude-sonnet-4.6",
        "Claude Sonnet 4.6 (Thinking)",
    ),
    "anthropic/claude-fable-5": ("claude-fable-5", "fable", "default"),
    "openai/gpt-5.6-sol-pro": ("gpt-5.6-sol-pro", "gpt-5.6-sol"),
    "openai/gpt-5.6-terra": ("gpt-5.6-terra", "gpt-5.6-terra-1m", "terra"),
    "x-ai/grok-4.5": ("grok-4.5", "grok-4-5", "grok-4.5-20260708"),
    "x-ai/grok-build-0.1": ("grok-build-0.1", "grok-build"),
    "deepseek/deepseek-v4-pro": (
        "deepseek-v4-pro",
        "deepseek-v4-pro-di",
        "deepseek-ai/DeepSeek-V4-Pro",
    ),
    "deepseek/deepseek-v4-flash": (
        "deepseek-v4-flash",
        "deepseek-v4-flash-di",
        "deepseek-ai/DeepSeek-V4-Flash",
    ),
    "qwen/qwen3.7-max": ("qwen3.7-max", "qwen/qwen3.7-max", "qwen3.7-max-di", "Qwen/Qwen3.7-Max"),
    "qwen/qwen3.7-plus": ("qwen3.7-plus", "qwen/qwen3.7-plus"),
    "qwen/qwen3.8-max-preview": (
        "qwen3.8-max-preview",
        "qwen3.8-max",
        "qwen/qwen3.8-max-preview",
        "Qwen/Qwen3.8-Max-Preview",
    ),
    "qwen/qwen3.6-flash": ("qwen3.6-flash", "qwen/qwen3.6-flash", "Qwen/Qwen3.6-Flash"),
    "minimax/minimax-m3": ("minimax-m3", "minimax-3"),
    "minimax/minimax-m2.7": ("minimax-m2.7", "minimax-2.7"),
    "xiaomi/mimo-v2.5-pro": ("mimo-v2.5-pro", "mimo-2.5-pro"),
    "google/gemini-3.5-flash": (
        "gemini-3.5-flash",
        "gemini-3.5-flash-1m",
        "Gemini 3.5 Flash (Low)",
        "Gemini 3.5 Flash (Medium)",
        "Gemini 3.5 Flash (High)",
    ),
    "google/gemini-3.1-pro": (
        "gemini-3.1-pro",
        "gemini-3.1-pro-high",
        "Gemini 3.1 Pro (Low)",
        "Gemini 3.1 Pro (High)",
    ),
    "moonshotai/kimi-k2.7-code": ("kimi-k2.7-code", "kimi"),
    "moonshotai/kimi-k3": ("kimi-k3", "k3", "kimi-3", "kimi-code/k3"),
    "z-ai/glm-5.2": ("glm-5.2", "glm5.2", "glm"),
}

# Recursion guard — panelists answer directly, no tools / no delegation.
WORKER_GUARD = (
    "[FUSION_PANEL][NO_DELEGATE][NO_TOOLS]\n"
    "You are a deliberation panelist. Give your direct, reasoned answer to the TASK. "
    "Do NOT use tools, APIs, or further delegation. Text answer only.\n\nTASK:\n"
)
