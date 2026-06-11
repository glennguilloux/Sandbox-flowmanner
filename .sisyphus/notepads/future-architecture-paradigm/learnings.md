# future-architecture-paradigm learnings

## Session conventions
- Plan selected because Task 1 was already checked in the plan.
- No inherited wisdom yet; append task findings after each verified delegation.

## 2026-06-11 Task 1 non-goal harness fix
- `scripts/validate_future_arch_docs.py` now checks exact required stop-gate phrases in `docs/future-architecture/01-paradigm-evaluation.md` instead of broad regexes that could match the decision paragraph.
- Missing stop gates now fail validation with the missing non-goal label and exact phrase, e.g. `missing non-goal/stop gate: no microservices default (No microservices default.)`.
- Added focused pytest coverage in `scripts/tests/test_validate_future_arch_docs.py` for current-pack success and removed Stop Gates failure.
- Verified with `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`, a temporary-copy negative run, and `python -m pytest scripts/tests/test_validate_future_arch_docs.py -q`.

## 2026-06-11 Task 1 NATS stop-gate wording fix
- `REQUIRED_NON_GOALS` now accepts both NATS gate wordings: `No NATS before outbox and event-schema stability.` and `No NATS before outbox/event-schema stability.`
- Missing NATS gate errors now include the label plus both accepted exact phrases, so single-line removal cannot pass silently.
- Focused pytest now covers current-pack success, slash-variant acceptance, full Stop Gates removal, and single NATS gate removal.
- Verified with real-pack validation, `python scripts/validate_future_arch_docs.py --self-test`, focused pytest, and temp-copy negative checks for single NATS removal plus full Stop Gates removal.
