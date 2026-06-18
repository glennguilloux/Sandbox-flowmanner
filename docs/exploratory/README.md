# Exploratory Testing

## Purpose

This directory stores exploratory session outputs per test automation strategy doc §8. Each session captures what was investigated, what broke, and what follow-ups should be added to scripted coverage.

## File naming convention

Use:

```text
<date>-<owner>-<charter>.md
```

Use the session template from strategy doc §15.3 when writing a new session file.

## Rolling charter backlog

- **CHX-01:** As a free user, do everything possible without paying; find a path to a paid feature.
- **CHX-02:** Send a mission with `model_preference` to each of: missing key, revoked key, expired key, model-id-that-does-not-exist.
- **CHX-03:** Interact with the chat stream and kill the tab at every possible moment; check for orphaned state in DB.
- **CHX-04:** With a sandbox session, deliberately trigger 401, 403, 404, 500 in turn; verify the UI handles each.
- **CHX-05:** Auth: refresh, expire, reuse-after-expiry, concurrent refresh from two devices.

## Status

No sessions recorded yet.
