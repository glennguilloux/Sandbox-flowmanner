Hubble.md — Deep Forensic Analysis

Here's what's genuinely clever and worth stealing from Ben Holmes' hubble.md repo, organized by category.

1. The Spec Pipeline: PRODUCT.md → TECH.md → Implementation

The pattern: A two-spec system where one doc owns observable behavior and the other owns implementation:

• specs/<id>/PRODUCT.md — pure user-facing behavior, numbered invariants, no implementation details at all."Behavior is the spec."
• specs/<id>/TECH.md — references PRODUCT.md's numbered invariants, maps them to actual modules/APIs/tests.Includes codebase map tables, commit-pinned links, affected packages, parallelization strategy.

Why it's clever:

• PRODUCT.md can be reviewed by non-engineers. TECH.md can be reviewed by engineers. No one doc tries to beboth.
• The constraint "do not include implementation in PRODUCT.md" is enforced by a skill (write-product-spec),not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.not by hand-waving — the agent literally won't let you drift.
• specs/<id>/ directories are keyed to GitHub issue numbers (gh-31) or kebab names(local-workspace-onboarding), so specs and issues are discoverable together.
• The to-issues skill then breaks those specs into vertical tracer-bullet slices — each issue is a thinend-to-end cut, not a horizontal layer.

What FlowManner could steal:

• The PRODUCT.md / TECH.md split for .hermes/plans/. Right now we have single plans that mix behavior andimplementation. Splitting them would let product review happen independently of engineering review.
• The specs/<id>/ directory convention — cleaner than our flat .hermes/plans/ for cross-referencing withissues.

────────────────────────────────────

2. Domain Documentation as Agent Infrastructure

The pattern: CONTEXT.md is a glossary and nothing else — domain terms, flagged ambiguities, explicit "avoid"aliases. No implementation details, no architecture, no process. Pure language consensus.

The key insight: agents hallucinate synonyms. If the codebase says "Workspace Folder" but the agent writes"project directory", you get drift. CONTEXT.md freezes the canonical vocabulary.

The docs/agents/domain.md file tells every skill: "read CONTEXT.md before you explore, use its vocabulary inyour output, flag contradictions against ADRs."

Why it's clever:

• The glossary is not a spec — it's explicitly "devoid of implementation details." It's just terms. Tinysurface area, huge impact.
• Flagged ambiguities sit at the top (e.g., "Workspace ≠ Cloud Sync — don't conflate these"). This preventsthe #1 real failure mode: two people (or two agents) using the same word for different things.
• The grill-with-docs skill updates CONTEXT.md inline during the grilling session — not as a batch afterward.Terms get captured as decisions crystallize.

What FlowManner could steal:

• A proper CONTEXT.md at the repo root. We have AGENTS.md (ops/process) but no shared domain glossary. Ouragents probably use different terms for "blueprint", "chat", "sandbox", etc. across sessions.

────────────────────────────────────

3. ADRs with Supersession Chains

The pattern: Each ADR has a Status: superseded by ADR-XXXX line at the top. ADR-0004 (per-embed iframesandboxing) → ADR-0005 (in-realm Shadow DOM) → ADR-0007 (workspace-local HTML apps). You can walk the chainand see how thinking evolved, not just the current state.

Why it's clever:

• Most repos either delete old ADRs (losing reasoning) or keep them without forward pointers (requiringarchaeology). The supersession chain gives you both the old reasoning and the path to current truth.
• The ADRs are short and opinionated. ADR-0004 is ~15 lines of prose that explains why an approach wasrejected, with explicit "Rejected because" sections.

What FlowManner could steal:

• We have some ADR-like decisions in memory/plan docs, but nothing with explicit supersession chains or the"three conditions required for an ADR" filter from grill-with-docs: hard to reverse, surprising withoutcontext, result of a real tradeoff. That filter prevents ADR sprawl.

────────────────────────────────────

4. Skill Architecture: Progressive Disclosure + Skill Chaining

The pattern: 15 skills, but the agent only loads the name+description (~53 tokens each) until it needs thefull content. Skills compose:

  review-readiness = simplify → comments → run checks
  done = changelog → commit → merge → cleanup

Why it's clever:

• review-readiness doesn't duplicate the simplify/comments logic — it calls those skills. Composition overcontent.
• ask-cc is brilliant: it shells out to the claude CLI for a taste judgment (naming, UI polish, prose) whenthe Hubble agent would otherwise guess. It's an escape hatch for subjective decisions, not a tool forobjective work.
• test-desktop-app describes CDP-based verification of the running Electron app — real executable validation,not "manually verify."

What FlowManner could steal:

• The review-readiness chain pattern (simplify → comments → checks) as a Hermes skill. We have simplify-codebut no composed review pipeline.
• The ask-cc pattern is interesting — delegating taste calls to a different model. We could do this withmcp_brain_process_task or delegate_task.

────────────────────────────────────

5. Issue Triaging as a Structured Skill

The pattern: The triage skill returns a single raw JSON object — no prose, no markdown, no explanation:

  ─ json
  {
    "state": "Ready to implement",
    "label": "ready-for-agent",
    "remove_labels": ["needs-triage"],
    "comment": "markdown body..."
  }

And the four states are crisp: Ready to implement | Ready to spec | Needs info | Wait to implement. Theboundary rule: "When evidence sits between states, choose the more cautious state."

Why it's clever:

• The triage skill is read-only — it never mutates the tracker. The human (or a separate skill) applies thelabels. Separation of analysis from action.
• Ready to spec vs Ready to implement is the key distinction most triage systems miss. "We know we want thisbut not how" is a different workflow from "we know what and how."
• The Needs info state requires listing the smallest set of concrete questions that would unblock re-triage.Not "we need more info" — specific questions.

What FlowManner could steal:

• This triage structure as a Hermes skill. Right now we just... read issues and talk about them. A structuredtriage output would make issue processing much more consistent.

────────────────────────────────────

6. The "Grill" Skill: Domain-Aware Interrogation

The pattern: grill-with-docs grills the user's plan against the existing domain model, not just generically.It:

1. Checks every term the user says against CONTEXT.md — if they say "account" but the glossary defines"Customer" and "User" separately, it calls it out.
2. Updates CONTEXT.md inline as terms are resolved — not batched.
3. Only offers to create an ADR when all three conditions are met (hard to reverse, surprising withoutcontext, result of a genuine tradeoff).

Why it's clever:

• This is the missing piece in most "AI helps me plan" setups: the agent checks your language consistency,not just your logic. It catches the "you said X here but your code does Y" contradictions.
• The ADR-gating rule prevents the common failure mode of agents generating ADRs for every trivial decision.

────────────────────────────────────

7. Deploy/Release as a Skill, Not a Script

The pattern: The release skill describes the exact flow: bump version → promote changelog → commit → tag →push → GitHub Actions takes over. The changelog skill is separate and feeds into it: write entries under ##[Unreleased] as work lands, not by scraping commits at release time.

Why it's clever:

• "Record what shipped as it lands, not by scraping commits at release time" is the right call. Retroactivechangelog generation always misses nuance.
• The done skill chains: changelog → commit → merge → cleanup → push. No separate "remember to update thechangelog" step.

────────────────────────────────────

Summary: What's Actually Novel vs. Just Well-Executed

  Pattern                              Novel?                    Our Gap?
  ───────────────────────────────────  ────────────────────────  ────────────────────────────────────────
  PRODUCT.md / TECH.md split           Well-executed, not novel  Yes — our plans mix behavior + impl
  CONTEXT.md as pure glossary          Novel framing             Yes — we have no domain glossary
  ADR supersession chains              Well-executed             Partial — we have some but no chains
  Skill chaining (review-readiness)    Well-executed             Yes — we have simplify-code but no chain
  ask-cc taste delegation              Novel pattern             Maybe — mcp_brain_process_task is
  ask-cc taste delegation              Novel pattern             Maybe — mcp_brain_process_task is
                                                                 similar
  grill-with-docs glossary             Novel                     Yes — no domain-aware grilling
  enforcement
  Inline changelog during work         Well-executed             Partial — we have SESSION-RITUAL.md

The two biggest things to steal are:

1. CONTEXT.md — a pure domain glossary that agents check before writing, preventing synonym driftindependently-reviewable specsindependently-reviewable specs
