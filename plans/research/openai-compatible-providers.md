# OpenAI-Compatible Providers Reference

All providers below accept OpenAI-format API keys and use the `/v1/chat/completions` endpoint pattern.
The backend's `chat_service.py` creates an `AsyncOpenAI(api_key=..., base_url=...)` client — any OpenAI-compatible endpoint works.

## Primary Providers

| Provider | Base URL | Key Prefix | Key Models | Pricing/M tokens |
|----------|----------|------------|------------|------------------|
| OpenAI | https://api.openai.com/v1 | sk- | gpt-4o, gpt-4o-mini, o1, o3-mini | $2.50-15 |
| Anthropic | https://api.anthropic.com/v1 | sk-ant- | claude-sonnet-4, claude-3.5-sonnet, claude-3-opus | $3-15 |
| DeepSeek | https://api.deepseek.com/v1 | sk- | deepseek-chat (v4), deepseek-reasoner | $0.27-1.10 |
| OpenRouter | https://openrouter.ai/api/v1 | sk-or- | 400+ models across all providers | Varies |
| Google AI | https://generativelanguage.googleapis.com/v1beta | AIza | gemini-2.5-pro, gemini-2.5-flash | Free tier |

## Secondary Providers (OpenAI-Compatible)

| Provider | Base URL | Key Prefix | Models |
|----------|----------|------------|--------|
| Groq | https://api.groq.com/openai/v1 | gsk_ | llama-4, mixtral, deepseek-r1, qwen |
| Together AI | https://api.together.xyz/v1 | sk- | llama-4, deepseek-r1, qwen-3, mistral (200+) |
| Fireworks AI | https://api.fireworks.ai/inference/v1 | fw_ | llama-4, qwen-3, deepseek, mixtral |
| DeepInfra | https://api.deepinfra.com/v1/openai | sk- | llama-4, qwen-3, wizardlm (cheapest) |
| xAI (Grok) | https://api.x.ai/v1 | xai- | grok-3, grok-3-mini |

## Key Models per Provider (2026)

### Groq (fastest inference)
- groq/llama-4-maverick (128K ctx, ~$0.20/M)
- groq/llama-4-scout (1M ctx, ~$0.15/M)
- groq/deepseek-r1-distill-llama-70b (131K ctx, ~$0.75/M)
- groq/mixtral-8x22b (65K ctx, ~$0.90/M)

### Together AI (broadest open-source)
- together/llama-4-maverick (128K ctx, ~$0.40/M)
- together/deepseek-r1 (131K ctx, ~$0.80/M)
- together/qwen-3-235b-a22b (131K ctx, ~$1.20/M)
- together/mixtral-8x22b (65K ctx, ~$0.60/M)

### DeepInfra (cheapest)
- deepinfra/llama-4-maverick (128K ctx, ~$0.12/M)
- deepinfra/qwen-3-32b (131K ctx, ~$0.15/M)
- deepinfra/wizardlm-2-8x22b (65K ctx, ~$0.05/M)

### Fireworks AI (structured output optimized)
- fireworks/llama-4-maverick (128K ctx, ~$0.30/M)
- fireworks/qwen-3-32b (131K ctx, ~$0.25/M)
