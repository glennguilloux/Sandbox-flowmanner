# Swarm in 30 seconds — Multi-Agent Debate Quick Start

> **The fastest way to see Flowmanner's most differentiated capability:** put two
> agents in a structured debate, scored by an LLM judge. No mission setup, no
> workflow graph — one `curl` and you have a consensus synthesis in seconds.

## Why this is the headline call

Flowmanner's swarm layer lets you orchestrate multiple specialized agents that
*argue* a topic, then an LLM judge scores each side and produces a synthesis.
The endpoint `POST /api/swarm/protocol/debate` is the single most distinctive
call in the API: it is real, callable, and returns a judge-scored result. This
page gets you from zero to a working debate in under a minute.

## Step 1 — One copy-paste curl

```bash
# 1. Grab two agent personality ids (the "swarm" is the product family name;
#    these ids come from GET /api/agent-personalities).
curl -s https://flowmanner.com/api/agent-personalities \
  | python3 -m json.tool | head -40

# 2. Start a debate. Replace the agent_*_id values with any two ids above.
#    Export your key first:  export FLOWMANNER_API_KEY="sk-..."
curl -X POST https://flowmanner.com/api/swarm/protocol/debate \
  -H "Authorization: Bearer $FLOWMANNER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Should we use GraphQL or REST for our new public API?",
    "agent_a_id": "software-it/code-review-assistant",
    "agent_a_name": "Code Review Assistant",
    "agent_b_id": "legal/contract-reviewer",
    "agent_b_name": "Contract Reviewer",
    "max_rounds": 2
  }'
```

Expected (200) response shape:

```json
{
  "debate_id": "debate-0a1b2c",
  "round_number": 2,
  "judge_verdict": "agent_a",
  "judge_score_a": 0.82,
  "judge_score_b": 0.71,
  "consensus_reached": true,
  "consensus_synthesis": "GraphQL fits read-heavy clients with nested data; REST is simpler to secure and cache. Default to REST, adopt GraphQL per-client where it pays off.",
  "status": "completed"
}
```

That's it — you just ran a multi-agent debate with an LLM judge in ~30 seconds.

## Step 2 — Pick your agents

List the available personalities and reuse their `id` directly in the debate
body. The `id` format is `<domain>/<slug>` (e.g. `software-it/code-review-assistant`).
Note the domain segment uses **hyphens** (`software-it`, not `software_it`) —
that is how `GET /api/agent-personalities` returns ids.

```bash
curl -s https://flowmanner.com/api/agent-personalities \
  -H "Authorization: Bearer $FLOWMANNER_API_KEY" \
  | python3 -c "import sys,json;[print(p['id'],'—',p['name']) for p in json.load(sys.stdin)]"
```

## Step 3 — Inspect a finished debate

```bash
curl https://flowmanner.com/api/swarm/protocol/debate/<debate_id> \
  -H "Authorization: Bearer $FLOWMANNER_API_KEY"
```

Returns every round: each agent's position, rebuttal, the judge's reasoning,
and per-round scores.

## Recorded-replay landing-demo spec

The "Swarm in 30 seconds" landing demo is a **recorded replay**, not a live
call, so it loads instantly and never depends on API-key provisioning or LLM
latency. Spec:

| Field | Value |
|-------|-------|
| **Demo type** | Recorded replay (pre-captured `POST /api/swarm/protocol/debate` request + response) |
| **Source call** | `POST /api/swarm/protocol/debate` with the Step 1 body |
| **Capture method** | Run the Step 1 curl against a staging backend, record the request JSON and the 200 response JSON |
| **Replay UI** | Single static panel: left = the curl + request JSON, right = the streamed rounds (position A → rebuttal B → judge verdict + synthesis), animated top-to-bottom |
| **Interactivity** | Copy-button on the curl; a "swap agents" dropdown that swaps `agent_a_id`/`agent_b_id` labels in the displayed curl (visual only — no live call) |
| **CTA** | "Get an API key" → signup; then the live Step 1 curl works unchanged |
| **Fallback** | If the recording is unavailable, the panel shows the curl + a note: "Replace `$FLOWMANNER_API_KEY` and run it — you'll get a judge-scored debate in ~30s" |
| **No fake output** | The synthesis shown is the *exact* recorded response; never synthesized for the demo |

## ⚠️ Naming note: "swarm" is the product family, not a request field

Older docs and the stale `openapi.json` referenced a `strategy` parameter with
values `parallel | sequential | debate`. **That endpoint (`POST /api/swarm/execute`)
was removed.** In the live API there is **no `strategy` parameter anywhere**, and
**no value `swarm`** to send. The live differentiator is the `debate` protocol
endpoint documented above. If you see a `strategy: "swarm"` example, it is
outdated — use `POST /api/swarm/protocol/debate` instead.

## Python SDK

```python
from flowmanner_api_client import FlowmannerClient

with FlowmannerClient("https://flowmanner.com") as fm:
    result = fm.debate(
        topic="Should we use GraphQL or REST for our new public API?",
        agent_a_id="software-it/code-review-assistant",
        agent_a_name="Code Review Assistant",
        agent_b_id="legal/contract-reviewer",
        agent_b_name="Contract Reviewer",
        max_rounds=2,
    )
    print(result["consensus_synthesis"])
```

See the [SDK README](../sdk-python/flowmanner-api-client/README.md) for install
and setup details.
