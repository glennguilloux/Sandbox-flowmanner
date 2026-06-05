# Flowmanner Sprint Plan - Sprint 1

**Sprint Goal:** Implement core mission execution and dashboard functionality (User-Value Epic 1 and 2)

**Sprint Duration:** 2026-05-01 to 2026-05-15 (14 days)

**Scrum Team:**
- Product Manager: John
- Business Analyst: Mary
- Developer: Amelia
- QA Engineer: Quinn
- Scrum Master: Bob

---

## Story Priority Classification

### Revenue-Critical (Must ship for revenue)
- Story 1.1: View Mission Cards (FR12, FR27)
- Story 1.2: Receive Real-Time Mission Updates (FR13, FR27)
- Story 2.1: View Dashboard Analytics (FR16)
- Story B.4: Implement Hybrid HTTP/SSE/Redis pub/sub (FR12-FR15, NFR3)

### Launch-Blocker (Must fix before launch)
- Story 1.3: Configure Mission Notifications (FR15, FR27)
- Story 1.4: View Mission ETA Displays (FR14)
- Story 2.2: Monitor Firefighting Metrics (FR17)
- Story A.1: Set up Postgres 16 plus Redis 7.2 plus Qdrant 1.7 (FR1-FR11)
- Story A.2: Implement Pydantic v2 Validation Layer (FR1-FR11)
- Story B.1: Set up FastAPI 0.136.0 with OpenAPI 3.0.3 Docs (FR20, NFR14)

### Nice-to-Have (Can defer to later sprints)
- Story 2.3: Handle Mission Edge Cases (FR18)
- Story 2.4: View Partner Revenue Dashboard (FR19)
- Story 3.1: Manage BYOK API Keys (FR22)
- Story 4.1: Export/Delete Personal Data (FR35)

---

## Sprint 1 Scope (Priority: Revenue-Critical plus Launch-Blockers)

1. Story 1.1: View Mission Cards (FR12, FR27)
2. Story 1.2: Receive Real-Time Mission Updates (FR13, FR27)
3. Story 2.1: View Dashboard Analytics (FR16)
4. Story B.4: Implement Hybrid HTTP/SSE/Redis pub/sub (FR12-FR15, NFR3)
5. Story 1.3: Configure Mission Notifications (FR15, FR27)
6. Story 1.4: View Mission ETA Displays (FR14)
7. Story 2.2: Monitor Firefighting Metrics (FR17)

**Total Stories:** 7
**Estimated Story Points:** 21 (assuming 3 points per story)

---

## Definition of Done (DoD)
- [ ] Code implemented per architecture.md (Categories 1-7)
- [ ] Unit tests written and passing (pytest)
- [ ] Code review completed (Amelia)
- [ ] QA testing passed (Quinn)
- [ ] Acceptance Criteria met (Given/When/Then)
- [ ] Committed to feature/flowmanner-architecture branch
- [ ] Party Mode sign-off received (all 5 roles)

---

## Sprint Backlog (from corrected epics.md)
- Total Epics: 10 (4 User-Value plus 6 Technical)
- Total Stories: 37+ (from epics.md)
- FR Coverage: 43/43 (100%)
- NFR Coverage: 21/21 (100%)

---

## Sprint Ceremonies
- **Sprint Planning:** 2026-05-01 (today)
- **Daily Standups:** 2026-05-01 to 2026-05-15, 09:00 UTC
- **Sprint Review:** 2026-05-15
- **Sprint Retrospective:** 2026-05-15
