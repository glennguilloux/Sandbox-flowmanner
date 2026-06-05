# Flowmanner Phase 4 — Sprint 2 Plan (May 16-30 2026)

## Sprint Goal
Deliver user-facing monetization features (subscription tiers, Stripe billing prep) and critical edge-case handling to improve user experience and enable revenue generation.

## Selected Stories (4 stories, 21 Fibonacci points)

| Story ID | Title | FR Coverage | Points | Owner | Status |
|----------|-------|-------------|--------|-------|--------|
| 2.3 | Handle Mission Edge Cases | FR18 | 5 | Dev Team | Todo |
| 2.4 | View Partner Revenue Dashboard | FR19 | 8 | Dev Team + QA | Todo |
| 3.2 | Select Subscription Tier | FR30 | 5 | Dev Team + UX | Todo |
| 3.1 | Manage BYOK API Keys | FR22 | 3 | Dev Team | Todo |

## Dependencies & Notes
- **3.2 (Sub Tier)** must complete before 3.3 (Stripe Billing) in Sprint 3
- **2.3 (Edge Cases)** builds on existing mission error handling from Sprint 1
- **2.4 (Partner Revenue)** requires new DB models for partner payouts (new table: `partner_revenue`)
- **3.1 (BYOK)** integrates with existing user settings; encrypt keys with AES-256

## Sprint Capacity
- Sprint Duration: 14 days (May 16-30 2026)
- Team: Hermes Agent (Lead), Dev Team, QA, UX
- Velocity: ~20 points/sprint (based on Sprint 1 completion of 7 stories)

## Definition of Done
- Code committed to `feature/flowmanner-architecture`
- Party Mode sign-off (5 roles per story)
- Unit tests with >80% coverage
- Story status updated in `story-status.md`

## Specialist Input (Harmonist Agents)
- **Business Analyst**: Prioritized 3.2 (Sub Tier) and 2.4 (Partner Revenue) for revenue impact
- **Backend Architect**: Noted 2.4 requires new DB schema; 3.1 needs encryption at rest
- **QA Verifier**: 2.3 (Edge Cases) needs 10+ edge case tests (API downtime, GPU unavailability)
