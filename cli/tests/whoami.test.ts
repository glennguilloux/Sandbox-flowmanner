/**
 * Tests for the `flowmanner whoami` command.
 *
 * Strategy: stub globalThis.fetch + pre-seed credentials, then invoke
 * the command's action handler directly so we can capture stdout.
 */
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";

process.env["FLOWMANNER_CONFIG_DIR"] = mkdtempSync(join("/tmp", "fm-whoami-"));

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

/** Capture what the command writes to stdout for a single run. */
async function captureWhoami(
  fetchImpl: typeof fetch,
  creds: { token: string; email: string; workspaceId?: string },
): Promise<{ stdout: string; stderr: string; exitCode: number | undefined }> {
  const { saveCredentials, clearCredentials } = await import(
    "../src/lib/config.js"
  );
  clearCredentials();
  saveCredentials(creds);

  globalThis.fetch = fetchImpl;

  const chunks: string[] = [];
  const errChunks: string[] = [];
  const origLog = console.log;
  const origErr = console.error;
  console.log = (...args: unknown[]) => chunks.push(args.join(" "));
  console.error = (...args: unknown[]) => errChunks.push(args.join(" "));
  const origExit = process.exitCode;
  let captured: { stdout: string; stderr: string; exitCode: number | undefined } = {
    stdout: "",
    stderr: "",
    exitCode: undefined,
  };

  try {
    const { Command } = await import("commander");
    const { registerWhoamiCommand } = await import(
      "../src/commands/whoami.js"
    );
    const program = new Command();
    registerWhoamiCommand(program);
    await program.parseAsync(["node", "test", "whoami"]);
  } finally {
    console.log = origLog;
    console.error = origErr;
    const code = process.exitCode;
    process.exitCode = origExit;
    captured = { stdout: chunks.join("\n"), stderr: errChunks.join("\n"), exitCode: code };
  }
  return captured;
}

test("whoami prints email, full_name, user_id, workspace_id — no drift warning", async () => {
  const { stdout, exitCode } = await captureWhoami(
    async () =>
      new Response(
        JSON.stringify({
          data: {
            id: 42,
            email: "alice@example.com",
            full_name: "Alice Example",
            workspace_id: "ws-shared",
          },
          error: null,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    { token: "jwt-1", email: "alice@example.com", workspaceId: "ws-shared" },
  );
  assert.equal(exitCode, undefined, "should not set a non-zero exit code");
  assert.match(stdout, /alice@example\.com/);
  assert.match(stdout, /Alice Example/);
  assert.match(stdout, /user_id: 42/);
  assert.match(stdout, /workspace_id: ws-shared/);
  // The dead workspace-drift warning must never print.
  assert.doesNotMatch(stdout, /differs from server/);
  assert.doesNotMatch(stdout, /note: stored workspace_id/);
});

test("whoami still works when stored workspace_id differs from server (no false drift warning)", async () => {
  // The audit (#6) caught that `me.workspace_id` is always undefined from
  // the backend, so the previous drift-check branch could never fire
  // truthfully. The fix removes the branch entirely. Even if/when the
  // backend adds workspace_id to UserResponse, this command shouldn't
  // print a "drift" warning without a tracked plan.
  const { stdout } = await captureWhoami(
    async () =>
      new Response(
        JSON.stringify({
          data: { id: 7, email: "bob@example.com" },
          error: null,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    { token: "jwt-2", email: "bob@example.com", workspaceId: "ws-stale" },
  );
  assert.match(stdout, /bob@example\.com/);
  assert.match(stdout, /user_id: 7/);
  assert.doesNotMatch(stdout, /workspace_id/);
  assert.doesNotMatch(stdout, /differs/);
});

test("whoami prints 'Not logged in' and exits 1 when credentials are missing", async () => {
  const { clearCredentials } = await import("../src/lib/config.js");
  clearCredentials();

  const errChunks: string[] = [];
  const origErr = console.error;
  console.error = (...args: unknown[]) => errChunks.push(args.join(" "));

  try {
    const { Command } = await import("commander");
    const { registerWhoamiCommand } = await import(
      "../src/commands/whoami.js"
    );
    const program = new Command();
    registerWhoamiCommand(program);
    await program.parseAsync(["node", "test", "whoami"]);
  } finally {
    console.error = origErr;
  }

  assert.equal(process.exitCode, 1);
  assert.match(errChunks.join("\n"), /Not logged in/);
  process.exitCode = undefined;
});
