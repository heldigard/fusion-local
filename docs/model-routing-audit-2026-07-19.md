# Model routing audit — 2026-07-19

This is the evidence ledger for Fusion and cheap-llm model selection. A live
catalog entry makes a model callable, not suitable. Promotion requires a
task-specific quality, reliability, latency, and token-cost result.

## Evidence snapshot

Artificial Analysis values below are Intelligence / Coding / Agentic indices
extracted from each model page on 2026-07-19.

| Model | Intelligence | Coding | Agentic | Routing decision |
|---|---:|---:|---:|---|
| GPT-5.6 Sol | 58.89 | 77.39 | 54.00 | Frontier subscription / ultra family |
| Kimi K3 | 57.11 | 76.24 | 50.07 | Default subscription generalist |
| GPT-5.6 Terra | 54.95 | 76.66 | 47.38 | Default subscription / coding |
| Claude Fable 5 | 59.86 | 76.49 | 52.81 | Ultra Anthropic seat |
| Claude Opus 4.8 | 55.69 | 74.25 | 47.18 | Subscription reasoning only; redundant with Fable in PAYG ultra |
| Claude Sonnet 5 | 53.35 | 71.55 | 46.69 | Coding/review subscription |
| Gemini 3.5 Flash | 50.20 | 70.14 | 37.45 | Fast/long-context subscription |
| GLM 5.2 | 51.09 | 68.76 | 43.06 | Default subscription / intelligence |
| Qwen 3.7 Max | 45.99 | 65.97 | 30.59 | PAYG diversity through ZenMux |
| DeepSeek V4 Pro | 44.27 | 59.36 | 36.36 | Value PAYG |
| MiniMax M3 | 44.44 | 58.57 | 35.36 | Cheap judge/panel candidate |
| MiMo V2.5 Pro | 42.24 | 60.19 | 29.11 | Subscription specialist only |
| DeepSeek V4 Flash | 40.28 | 56.17 | 31.06 | Cheap transport/judge |
| Qwen 3.7 Plus | 38.98 | 55.86 | 20.81 | Remove from automatic panels |
| MiniMax M2.7 | 38.13 | 52.62 | 25.58 | Superseded by M3; manual legacy seat only |
| Tencent Hy3 | 41.23 | 58.80 | 30.73 | No default advantage over DS Flash/M3 |
| Step 3.7 Flash | 30.27 | 39.57 | 21.53 | Reject |

Sources:

- https://artificialanalysis.ai/models
- https://artificialanalysis.ai/models/gpt-5-6-sol
- https://artificialanalysis.ai/models/kimi-k3
- https://artificialanalysis.ai/models/glm-5-2
- https://artificialanalysis.ai/models/minimax-m3
- https://artificialanalysis.ai/models/deepseek-v4-flash
- https://artificialanalysis.ai/models/qwen3-7-max
- https://artificialanalysis.ai/models/step-3-7-flash

## DeepSWE v1.1: long-horizon coding efficiency

DeepSWE v1.1 evaluates 113 original engineering tasks across 91 repositories
and five languages. The following values are pass@1 and observed average API
cost per task under the common mini-swe-agent harness, updated 2026-07-17.

| Model | Pass@1 | Avg cost/task | Routing implication |
|---|---:|---:|---|
| GPT-5.6 Sol | 73% | $8.39 | Best difficult-coding subscription brain |
| Claude Fable 5 | 70% | $21.63 | Premium only; poor automatic cost efficiency |
| GPT-5.6 Terra | 70% | $4.95 | Same score as Fable at 23% of its cost |
| Kimi K3 | 69% | $4.65 | Strong subscription specialist |
| GPT-5.6 Luna | 67% | $3.03 | Excellent fast/value hand |
| Claude Opus 4.8 | 59% | $13.22 | Subscription reasoning diversity, not PAYG value |
| Claude Sonnet 5 | 54% | $26.40 | Subscription review/coding only |
| Grok 4.5 | 54% | $2.42 | Efficient coding specialist |
| GLM 5.2 | 44% | $3.92 | General reasoning diversity |
| Gemini 3.5 Flash | 37% | $7.34 | Fast/long-context diversity, not primary coder |

Fable costs about 2.58x Sol per DeepSWE task while scoring three points lower,
and about 4.37x Terra for the same score. Anthropic also states that Fable was
included in Pro/Max/Team usage only through 2026-07-07; afterward it uses
metered usage credits. It is therefore excluded from every automatic
subscription profile and reserved for explicit `ultra` PAYG escalation.

Sources:

- https://deepswe.datacurve.ai/
- https://artificialanalysis.ai/agents/coding-agents
- https://www.anthropic.com/news/redeploying-fable-5
- https://support.claude.com/en/articles/14552983-models-usage-and-limits-in-claude-code

## ZenMux provider bindings

The public `GET /api/v1/models` catalog was checked directly. Important exact
IDs and conservative fallback prices in USD per million input/output tokens:

| ZenMux ID | Context | Input | Output | Status |
|---|---:|---:|---:|---|
| `kuaishou/kat-coder-air-v2.5` | 256K | 0.135 | 0.540 | Coding experiment |
| `kuaishou/kat-coder-pro-v2.5` | 256K | 0.444 | 1.776 | Test only after Air passes |
| `bytedance/doubao-seed-2.1-pro` | 256K | 0.423 | 2.113 | Shadow experiment |
| `bytedance/doubao-seed-2.1-turbo` | 256K | 0.423 | 2.113 | Shadow experiment |
| `baidu/ernie-5.1` | 128K | 0.637 | 2.336 | Hold; no independent score |
| `x-ai/grok-build-0.1` | 256K | 1.000 | 2.000 | Coding specialist, not a general judge |
| `qwen/qwen3.7-plus` | 1M | 0.412 | 1.648 | Remove from automatic panels |
| `qwen/qwen3.7-max` | 1M | 0.431 | 1.292 | PAYG diversity |
| `tencent/hy3` | 256K | 0.132 | 0.530 | Hold; dominated on total efficiency |
| `stepfun/step-3.7-flash` | 256K | 0.135 | 0.776 | Reject |
| `minimax/minimax-m3` | 1M | 0.275 | 1.098 | Cheap panel |
| `z-ai/glm-5.2` | 1M | 0.980 | 3.080 | Intelligence fallback |

Tiered prices use the highest published text-token tier so telemetry does not
understate spend. OpenRouter publishes KAT under `kwaipilot/...`; ZenMux uses
`kuaishou/...`. cheap-llm resolves that difference only at the transport edge.

Sources:

- https://zenmux.ai/api/v1/models
- https://zenmux.ai/docs/api/openai/openai-list-models.html
- https://zenmux.ai/kuaishou/kat-coder-air-v2.5
- https://zenmux.ai/kuaishou/kat-coder-pro-v2.5
- https://zenmux.ai/bytedance/doubao-seed-2.1-pro
- https://zenmux.ai/bytedance/doubao-seed-2.1-turbo

## Approved routing

Subscription profiles:

- `balanced`: Claude Sonnet 5, Kimi K3, GLM 5.2.
- `coding`: GPT-5.6 Terra, Claude Sonnet 5, Kimi K3, Grok Build.
- `reasoning`: Claude Opus 4.8, GPT-5.6 Sol, Gemini 3.5 Flash, Kimi K3, GLM 5.2.
- `fast`: GPT-5.6 Luna, Gemini 3.5 Flash, GLM 5.2.
- `specialists`: Kimi K3, GLM 5.2, MiMo V2.5 Pro, Grok Build.

Live protocol checks passed for direct Claude Sonnet 5, Opus 4.8, and Fable 5,
plus Antigravity Gemini 3.5 Flash, Gemini 3.1 Pro, Claude Opus 4.6, and Claude
Sonnet 4.6. A successful Fable call is not evidence of subscription coverage:
Anthropic included it through 2026-07-07 and meters it through usage credits
afterward. Fusion therefore blocks `claude-fable` from subscription lane 1 and
keeps Fable only in the explicit PAYG `ultra` preset. Antigravity exposes no
Gemini 3.5 Pro in its current inventory. Its Claude 4.6 seats remain
explicit/manual because the newer direct Claude seats are stronger. The default
`balanced` panel moved from Terra to Sonnet after a 3/3 end-to-end comparison
reduced wall time from 44.55s to 38.93s while adding an independent family for
the usual Codex controller.

PAYG presets:

- `cheap`: DeepSeek V4 Flash (DeepInfra) + MiniMax M3 (ZenMux).
- `payg`: DeepSeek V4 Pro first-party + Qwen 3.7 Max (ZenMux).
- `intelligence`: Grok 4.5 + GPT-5.6 Terra + GLM 5.2.
- `ultra`: Claude Fable 5 + GPT-5.6 Sol Pro + Grok 4.5.

## Promotion gates

KAT, Doubao, ERNIE, and other unscored releases stay experimental. They must
not enter cheap-llm's default cascade or a Fusion preset until a relevant task
pack measures:

1. Exact-schema and instruction success rate.
2. Coding correctness on bounded repository tasks, not only short JSON tasks.
3. Agentic completion rate and retry count.
4. Median and p95 latency.
5. Input/output tokens and actual provider cost per successful task.
6. Provider error rate, context behavior, and model-ID stability.

The existing cheap_bench classification/JSON pack is suitable for judges and
distillers. It is not sufficient evidence for promoting a coding-agent model.
