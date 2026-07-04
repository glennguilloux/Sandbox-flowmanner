# LEGACY

## Purpose

`docs/LEGACY.md` tracks test cases retired from active enforcement per test automation strategy doc §5.1. A retired case is not deleted from history; it is intentionally recorded with the reason and approval for the retirement.

## Required fields per case

- Case ID
- Original ticket
- Why retired
- Who approved
- Date

## Retirement table format

| Case ID | Original ticket | Why retired | Who approved | Date |
|---|---|---|---|---|
| TC-PLACEHOLDER-000 | Placeholder only | Illustrative placeholder; no real retirement recorded here. | Placeholder only | YYYY-MM-DD |

## Re-enable policy

A LEGACY case is never silently re-enabled. Bringing it back requires a PR that links the new bug or audit finding, re-implements or un-quarantines the test, and removes the LEGACY entry in the same PR, as required by §5.1.

## Status

No retired cases yet.
