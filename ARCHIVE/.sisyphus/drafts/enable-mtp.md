# Draft: Enable MTP for Qwen3.6-27B

## Requirements (confirmed)
- User has llama.cpp at /home/glenn/.unsloth/llama.cpp (build b8955, Unsloth prebuilt, CUDA 13)
- User has a running llama-server at /mnt/apps/luce-llama.cpp/ with Qwen_Qwen3.6-27B-Q4_K_M.gguf
- Running as systemd-style process: llama-server --model /mnt/apps/models/Qwen_Qwen3.6-27B-Q4_K_M.gguf --host 0.0.0.0 --port 11434 --ctx-size 32768 --gpu-layers 99 --flash-attn on --spec-type ngram-simple --draft-max 8 --draft-min 3
- Hardware: 2x NVIDIA GeForce RTX 5060 Ti (16GB each) = 32GB total VRAM
- Current model: Qwen3.6-27B-UD-Q4_K_XL.gguf (17GB) at /home/glenn/models/
- Current model in use: Qwen_Qwen3.6-27B-Q4_K_M.gguf at /mnt/apps/models/
- User wants to enable MTP (Multi-Token Prediction) for speed gains

## Technical Decisions
- MTP requires BOTH a compatible llama.cpp build AND an MTP-enabled GGUF model
- Current llama.cpp (b8955) is Unsloth prebuilt - may or may not have MTP support
- Current GGUF models are standard Q4 variants - NOT MTP-enabled (no NextN heads)
- Need MTP-specific GGUF files (Q8nextn variants or models with MTP heads baked in)
- Key PRs: #22400 (prerequisite for GDN models) and #22673 (main MTP support)
- Community fork nickstx/llama.cpp branch "crucible" has both PRs merged
- Need to benchmark before/after to validate speedup

## Research Findings
- MTP merged to llama.cpp master as of May 2026 (beta)
- Qwen3.6-27B-MTP models available on HuggingFace (localweights org)
- Need Q8nextn quant variants for best acceptance rates
- Expected speedup: 1.5x-2x on predictable text, ~1.13x-1.71x reported
- VRAM overhead: MTP heads add ~10-20% more VRAM usage
- Current setup uses ngram speculative decoding (--spec-type ngram-simple), NOT MTP
- RTX 5060 Ti (16GB x2) should handle 27B Q4 + MTP heads within 32GB VRAM

## Open Questions
- Should we rebuild llama.cpp from MTP branch or use community fork?
- Which MTP GGUF quant to download? (IQ4_XS-Q8nextn, Q5_K_M, etc.)
- Should we keep ngram spec as fallback?
- What's the service management for the running llama-server? (systemd? docker?)

## Scope Boundaries
- INCLUDE: MTP-enabled llama.cpp build, MTP GGUF download, server config update, benchmark
- EXCLUDE: Model training, re-quantizing, changing model family

## Current Infrastructure
- llama-server running on HOMELAB (NOT VPS)
- Host: homelab at 10.0.4.1 (Docker gateway IP)
- Port: 11434, bound to 0.0.0.0
- Model: Qwen_Qwen3.6-27B-Q4_K_M.gguf — Qwen 3.6 27B, Q4_K_M quantization, full GPU offload
- API: OpenAI-compatible at /v1/
- Reachability: Backend container hits it at http://10.0.4.1:11434 via the glenn_workflows-web Docker network
- Backend connects via OLLAMA_BASE_URL=http://ollama:11434 (Docker network resolution)
- Hardware: 2x NVIDIA GeForce RTX 5060 Ti (16GB each) = 32GB total VRAM on homelab
