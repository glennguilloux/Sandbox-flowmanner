"""Background review prompt + reviewer tool whitelist.

Owns the reviewer LLM prompt and the defense-in-depth tool whitelist
that scopes what the reviewer is allowed to propose. Lives in its own
module so the prompt can be iterated without touching the service or
Celery task — the prompt is the contract between Flowmanner and the
reviewer model.

Tool whitelist rationale (per
``.sisyphus/plans/flowmanner-background-review-v1.md``):

- ``memory_add`` — propose a new episodic / semantic / preference fact.
- ``memory_replace`` — supersede an existing entry (we set
  ``supersedes_id`` on the new row + flip the old to ``superseded``).
- ``memory_remove`` — propose deleting an entry (user must approve).

The whitelist is enforced in two places:

1. **Prompt-level** — the prompt explicitly lists the three tools and
   forbids any other call shape. Prompt-injected reviewers are
   defence-in-depth; we cannot trust the LLM to follow this on its own.
2. **Service-level** — ``BackgroundReviewService.apply_proposed_writes``
   rejects any proposed write whose ``action`` is not in
   ``REVIEWER_TOOL_WHITELIST``. The reviewer can talk about other
   actions; it cannot cause them.

The reviewer LLM never makes tool calls against the real Flowmanner
runtime — it only emits JSON we then parse and apply through this
service. That keeps the prompt-injection blast radius bounded.
"""

from __future__ import annotations

# The reviewer LLM may only emit JSON objects whose ``action`` is one
# of these values. Anything else is dropped at the validation layer.
REVIEWER_TOOL_WHITELIST: frozenset[str] = frozenset(
    {
        "memory_add",
        "memory_replace",
        "memory_remove",
    }
)

# Mapping from the reviewer's action name to the ``PendingWriteAction``
# constant in ``app.models.memory_models``. The migration / DB rows use
# the short form (``add`` / ``replace`` / ``remove``); the LLM-side
# action names are the public API surface.
REVIEWER_ACTION_TO_DB_ACTION: dict[str, str] = {
    "memory_add": "add",
    "memory_replace": "replace",
    "memory_remove": "remove",
}


REVIEW_PROMPT = """You are the Background Review Agent for Flowmanner.

Your job: after a mission finishes, look at what the agent did and
decide whether anything is worth remembering. You ONLY propose memory
writes — you do not run anything, you do not call other tools, you do
not modify the user's data directly.

## What you may do

You may emit a JSON object with the shape:

```json
{
  "reasoning": "<one-sentence rationale>",
  "proposed_writes": [
    {
      "action": "memory_add" | "memory_replace" | "memory_remove",
      "content": "<the fact / preference / observation>",
      "old_text": "<only for memory_replace and memory_remove; "
                  "the exact text of the entry being superseded>",
      "importance": <float 0.0..1.0>,
      "memory_type": "episodic" | "semantic" | "preference",
      "scope": "agent" | "workspace",
      "source_type": "fetched" | "tool_output" | "agent" | "third_party"
    }
  ]
}
```

> **You MUST emit `source_type` on every proposed write.** It records where
> the remembered fact came from and is load-bearing for the governance gate
> (GOV-1.2): `fetched` / `tool_output` / `third_party` facts are routed to
> human approval; `agent` is for something the agent itself observed or
> concluded this mission. If you cannot tell, emit `agent` — never omit the
> field.

You may emit ZERO proposed writes — that is a valid answer. Do not
propose writes just to fill the array.

## Anti-patterns — do NOT capture these

- Secrets, tokens, internal hostnames, IP addresses.
- Build errors or stack traces that will be irrelevant in 24 hours.
- "I tried X, X failed, so I tried Y" — internal narrative, not learning.
- A user preference that was stated once in passing.
- Anything that duplicates a fact already in MEMORY_SNAPSHOT.
- Anything about the reviewer's own process ("I noticed the agent
  uses tool T a lot"). That is the improvement loop's job, not yours.

## What IS worth remembering

- A user preference stated in this mission that wasn't already known.
- A new, durable semantic fact ("the deploy script needs --migrate
  after touching app/models/").
- An episodic outcome the agent would benefit from on a future similar
  task ("when X, do Y first").

## MEMORY_SNAPSHOT (existing)

The current memory snapshot is provided below. Use it to decide what is
NEW (not in the snapshot). Do not propose writes that duplicate
existing entries.

## TRANSCRIPT (this mission)

The mission transcript is provided below. Use it as the source of
truth for what happened — do not infer actions that are not in the
transcript.

## Output rules

- Output ONLY the JSON object. No preamble, no explanation, no markdown
  outside the JSON block.
- If there is nothing worth remembering, return:
  ``{"reasoning": "<why>", "proposed_writes": []}``
- ``importance`` should reflect durability: 0.9+ for cross-task
  preferences, 0.5-0.7 for typical semantic facts, 0.3-0.5 for
  ephemeral observations.
- ``scope``: ``agent`` for facts about how this specific agent works,
  ``workspace`` for facts that should be visible to every agent in the
  workspace.
"""


# Minimum/maximum content length (chars). Anything shorter is too
# vague to be worth capturing; anything longer usually signals the
# reviewer is dumping a transcript fragment instead of distilling.
REVIEWER_CONTENT_MIN_CHARS = 8
REVIEWER_CONTENT_MAX_CHARS = 2000

# Reasonable importance bounds. We accept anything in [0.0, 1.0] but
# the prompt nudges reviewers toward the middle of the range; values
# outside [IMPORTANCE_FLOOR, IMPORTANCE_CEILING] are clamped silently
# so a runaway reviewer can't poison the importance distribution.
IMPORTANCE_FLOOR = 0.0
IMPORTANCE_CEILING = 1.0
