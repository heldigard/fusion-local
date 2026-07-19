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
HTTP_REFERER = "https://github.com/heldigard/fusion-local"
HTTP_TITLE = "fusion-local"

# Lane 1: $0 subscription workers, diverse families. Routed via config.ROUTER
# (codex=gpt-5.x, agy=gemini, kimic=kimi, zai=glm, grok=xAI).
PANEL_SUBS: list[str] = ["codex-spark", "agy35-flash", "kimic", "zai", "grok"]

# Cross-CLI override for lane-1 (mirrors FUSION_ROUTER semantics):
# unset → PANEL_SUBS default; "" → disable lane-1; "a,b" → custom worker modes.
PANEL_SUBS_ENV = "FUSION_PANEL_SUBS"

# Lane 2: PAYG fallback (HTTP direct) — universal cross-CLI. deepseek-v4-pro is
# first-party api.deepseek.com (same weights, no OpenRouter markup); other seats
# use OpenRouter. cheap/intelligence/ultra presets are explicit so the controller
# can pick cost vs depth intentionally. Cost tiers (output $/M):
#   cheap        ~$0.15-1.28  — economical open models
#   payg         ~$0.87-3.75  — open capable (default deliberation)
#   intelligence ~$6-15       — frontier-accessible, NO premium $25-50/M seats
#   ultra        ~$6-50       — full frontier incl. premium closed (fable/sol-pro/opus)
PANEL_PAYG: list[tuple[str, str, str, str]] = [
    ("deepseek-v4-pro", DEEPSEEK_URL, "deepseek-v4-pro", DEEPSEEK_KEY_ENV),
    ("qwen3.7-max", OPENROUTER_URL, "qwen/qwen3.7-max", OPENROUTER_KEY_ENV),
]

PANEL_CHEAP: list[tuple[str, str, str, str]] = [
    ("deepseek-v4-flash-di", DEEPINFRA_URL, "deepseek-ai/DeepSeek-V4-Flash", DEEPINFRA_KEY_ENV),
    ("qwen3.7-plus", OPENROUTER_URL, "qwen/qwen3.7-plus", OPENROUTER_KEY_ENV),
    ("minimax-m3", OPENROUTER_URL, "minimax/minimax-m3", OPENROUTER_KEY_ENV),
    ("mimo-v2.5-pro", OPENROUTER_URL, "xiaomi/mimo-v2.5-pro", OPENROUTER_KEY_ENV),
]

PANEL_ULTRA: list[tuple[str, str, str, str]] = [
    ("claude-fable-5", OPENROUTER_URL, "anthropic/claude-fable-5", OPENROUTER_KEY_ENV),
    ("claude-opus-4.8", OPENROUTER_URL, "anthropic/claude-opus-4.8", OPENROUTER_KEY_ENV),
    ("gpt-5.6-sol-pro", OPENROUTER_URL, "openai/gpt-5.6-sol-pro", OPENROUTER_KEY_ENV),
    ("gemini-pro-latest", OPENROUTER_URL, "~google/gemini-pro-latest", OPENROUTER_KEY_ENV),
    ("grok-4.5", OPENROUTER_URL, "x-ai/grok-4.5", OPENROUTER_KEY_ENV),
]

# Intelligence: frontier-accessible panel for medium-high complexity. 4 families
# (xAI, Google, OpenAI, DeepSeek), all frontier/open-capable, deliberately
# EXCLUDING the premium closed seats (claude-fable-5 $50, gpt-5.6-sol-pro $30,
# claude-opus-4.8 $25 per M output) that ultra reserves for high-stakes work.
# Roughly 5x cheaper than ultra per deliberation while keeping 2 frontier voices.
PANEL_INTELLIGENCE: list[tuple[str, str, str, str]] = [
    ("grok-4.5", OPENROUTER_URL, "x-ai/grok-4.5", OPENROUTER_KEY_ENV),
    ("gemini-pro-latest", OPENROUTER_URL, "~google/gemini-pro-latest", OPENROUTER_KEY_ENV),
    ("gpt-5.6-terra", OPENROUTER_URL, "openai/gpt-5.6-terra", OPENROUTER_KEY_ENV),
    ("deepseek-v4-pro", DEEPSEEK_URL, "deepseek-v4-pro", DEEPSEEK_KEY_ENV),
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
    "codex-spark": ("gpt-5.6-terra", "openai/gpt-5.6-terra"),
    "agy35-flash": ("gemini-3.5-flash", "google/gemini-3.5-flash"),
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
    "grok": ("grok-4.5", "x-ai/grok-4.5"),
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
    "anthropic/claude-fable-5": ("claude-fable-5", "fable", "default"),
    "openai/gpt-5.6-sol-pro": ("gpt-5.6-sol-pro", "gpt-5.6-sol"),
    "openai/gpt-5.6-terra": ("gpt-5.6-terra", "gpt-5.6-terra-1m", "terra"),
    "x-ai/grok-4.5": ("grok-4.5", "grok-4-5", "grok-4.5-20260708"),
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
    "minimax/minimax-m3": ("minimax-m3", "minimax-3"),
    "xiaomi/mimo-v2.5-pro": ("mimo-v2.5-pro", "mimo-2.5-pro"),
    "google/gemini-3.5-flash": ("gemini-3.5-flash", "gemini-3.5-flash-1m"),
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
