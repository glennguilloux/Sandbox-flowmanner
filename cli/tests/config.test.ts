/**
 * Tests for src/lib/config.ts — credentials round-trip + base URL.
 *
 * Each test uses a fresh FLOWMANNER_CONFIG_DIR via tmpdir, so tests
 * are isolated and don't clobber a real user's ~/.flowmanner/.
 */
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

let configDir: string;

before(() => {
  configDir = mkdtempSync(join(tmpdir(), "fm-config-"));
  process.env["FLOWMANNER_CONFIG_DIR"] = configDir;
});

after(() => {
  if (existsSync(configDir)) rmSync(configDir, { recursive: true });
});

test("saves and loads credentials", async () => {
  const { saveCredentials, loadCredentials, clearCredentials } = await import(
    "../src/lib/config.js"
  );
  saveCredentials({ token: "jwt-1", email: "a@b.com" });
  const loaded = loadCredentials();
  assert.ok(loaded);
  assert.equal(loaded.token, "jwt-1");
  assert.equal(loaded.email, "a@b.com");
  clearCredentials();
  assert.equal(loadCredentials(), null);
});

test("persists workspace_id when supplied", async () => {
  const { saveCredentials, loadCredentials, clearCredentials } = await import(
    "../src/lib/config.js"
  );
  saveCredentials({ token: "jwt-2", email: "c@d.com", workspaceId: "ws-123" });
  const loaded = loadCredentials();
  assert.ok(loaded);
  assert.equal(loaded.workspaceId, "ws-123");
  clearCredentials();
});

test("base URL defaults to https://flowmanner.com", async () => {
  const { getBaseUrl } = await import("../src/lib/config.js");
  assert.equal(getBaseUrl(), "https://flowmanner.com");
});

test("base URL override persists", async () => {
  const { getBaseUrl, setBaseUrl } = await import("../src/lib/config.js");
  setBaseUrl("http://localhost:8000");
  assert.equal(getBaseUrl(), "http://localhost:8000");
  // Reset so other tests see the default.
  setBaseUrl("https://flowmanner.com");
});