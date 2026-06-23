/**
 * Tests for the v2 envelope unwrap + error mapping in lib/api.ts.
 *
 * We don't hit a real backend. Instead we monkey-patch global.fetch
 * and run assertions against the wrapper.
 */
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";

// Each test sets FLOWMANNER_BASE_URL via a custom config + token so
// apiRequest doesn't bail on NotAuthenticated.
process.env["FLOWMANNER_CONFIG_DIR"] = await (async () => {
  const { mkdtempSync } = await import("node:fs");
  const { join } = await import("node:path");
  return mkdtempSync(join("/tmp", "fm-test-"));
})();

// Pre-seed credentials by writing to the conf store directly.
await import("../src/lib/config.js").then((m) =>
  m.saveCredentials({ token: "test-jwt", email: "test@example.com" }),
);

// Reset fetch after each test.
const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

test("unwraps v2 success envelope and returns data", async () => {
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        data: { id: "abc", title: "Hello" },
        meta: { request_id: "r1", timestamp: "2026-06-23T00:00:00Z" },
        error: null,
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  const { apiRequest } = await import("../src/lib/api.js");
  const out = await apiRequest<{ id: string; title: string }>("/api/v2/blueprints/abc");
  assert.deepEqual(out, { id: "abc", title: "Hello" });
});

test("passes through plain (non-enveloped) JSON", async () => {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  const { apiRequest } = await import("../src/lib/api.js");
  const out = await apiRequest<{ status: string }>("/api/health");
  assert.deepEqual(out, { status: "ok" });
});

test("maps v2 error envelope to FlowmannerApiError", async () => {
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        data: null,
        error: {
          code: "BLUEPRINT_NOT_FOUND",
          message: "No blueprint with id foo",
          details: { blueprint_id: "foo" },
        },
        meta: { request_id: "r2", timestamp: "2026-06-23T00:00:00Z" },
      }),
      { status: 404, headers: { "content-type": "application/json" } },
    );
  const { apiRequest, FlowmannerApiError } = await import("../src/lib/api.js");
  await assert.rejects(
    apiRequest("/api/v2/blueprints/foo"),
    (err: unknown) => {
      assert.ok(err instanceof FlowmannerApiError);
      assert.equal(err.status, 404);
      assert.equal(err.code, "BLUEPRINT_NOT_FOUND");
      assert.deepEqual(err.details, { blueprint_id: "foo" });
      return true;
    },
  );
});

test("attaches Authorization header from stored credentials", async () => {
  let capturedAuth: string | null = null;
  globalThis.fetch = async (_url, init) => {
    const headers = init?.headers as Record<string, string> | undefined;
    capturedAuth = headers?.["Authorization"] ?? null;
    return new Response(JSON.stringify({ data: {}, error: null }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const { apiRequest } = await import("../src/lib/api.js");
  await apiRequest("/api/v2/auth/me");
  assert.equal(capturedAuth, "Bearer test-jwt");
});

test("204 No Content returns undefined", async () => {
  globalThis.fetch = async () => new Response(null, { status: 204 });
  const { apiRequest } = await import("../src/lib/api.js");
  const out = await apiRequest("/api/v2/blueprints/abc", { method: "DELETE" });
  assert.equal(out, undefined);
});

test("NotAuthenticatedError when credentials are missing", async () => {
  const { clearCredentials } = await import("../src/lib/config.js");
  clearCredentials();
  const { apiRequest, NotAuthenticatedError } = await import("../src/lib/api.js");
  await assert.rejects(
    apiRequest("/api/v2/blueprints/"),
    (err: unknown) => err instanceof NotAuthenticatedError,
  );
  // Restore for downstream tests.
  await import("../src/lib/config.js").then((m) =>
    m.saveCredentials({ token: "test-jwt", email: "test@example.com" }),
  );
});