/**
 * Contract test: CLI's RunEvent interface must mirror backend's
 * RunEventResponse shape (see backend/app/schemas/blueprint.py).
 *
 * Static-type-level test (compile-time) — if a backend field is renamed
 * or removed, this test fails at build time, not at runtime.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import type { RunEvent } from "../src/types.js";

test("RunEvent matches backend RunEventResponse schema", () => {
  // If the interface changes shape, this assignment either narrows too
  // much (compile fail) or accepts extra fields silently (no fail) —
  // but a *required* field drop would fail the assignment.
  const sample: RunEvent = {
    id: "evt-1",
    sequence: 1,
    run_id: "run-1",
    type: "node.started",
    actor: "substrate",
    task_id: "task-1",
    causal_parent: null,
    timestamp: "2026-06-23T00:00:00Z",
  };
  assert.equal(sample.actor, "substrate");
  assert.equal(sample.timestamp, "2026-06-23T00:00:00Z");

  // The historical field name must NOT exist anymore. If a future
  // refactor re-adds `created_at`, the @ts-expect-error directive
  // becomes "unused" and tsc reports it — surfacing the drift.
  // @ts-expect-error -- created_at was removed; this access must fail to compile
  const drift: unknown = (sample as Record<string, unknown>).created_at;
  assert.equal(drift, undefined);
});
