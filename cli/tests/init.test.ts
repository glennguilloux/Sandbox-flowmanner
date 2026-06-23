/**
 * Smoke tests for `flowmanner init` — scaffold produces the right
 * files in the right place.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("init creates the expected project files", async () => {
  // Run the CLI in a sub-process against a tmpdir so we don't touch
  // the real filesystem.
  const { spawnSync } = await import("node:child_process");
  const dir = await mkdtemp(join(tmpdir(), "fm-init-"));
  const cliBin = join(import.meta.dirname, "..", "bin", "flowmanner.js");

  const result = spawnSync(
    "node",
    [cliBin, "init", "demo", "--template", "solo"],
    { cwd: dir, encoding: "utf8" },
  );
  assert.equal(result.status, 0, `init failed: ${result.stderr}`);

  const target = join(dir, "demo");
  const yamlStat = await stat(join(target, "flowmanner.yaml"));
  assert.ok(yamlStat.isFile());

  const readme = await readFile(join(target, "README.md"), "utf8");
  assert.match(readme, /Quick start/);

  const gitignore = await readFile(join(target, ".gitignore"), "utf8");
  assert.match(gitignore, /\.flowmanner\//);

  const yaml = await readFile(join(target, "flowmanner.yaml"), "utf8");
  assert.match(yaml, /version: 1/);
  assert.match(yaml, /name: "?demo"?/);

  await rm(dir, { recursive: true });
});

test("init --here scaffolds into cwd without creating a subdirectory", async () => {
  const { spawnSync } = await import("node:child_process");
  const dir = await mkdtemp(join(tmpdir(), "fm-init-here-"));
  const cliBin = join(import.meta.dirname, "..", "bin", "flowmanner.js");

  const result = spawnSync(
    "node",
    [cliBin, "init", "x", "--here", "--template", "solo"],
    { cwd: dir, encoding: "utf8" },
  );
  assert.equal(result.status, 0, `init --here failed: ${result.stderr}`);

  // Files land in cwd, NOT in a subdirectory.
  const yamlStat = await stat(join(dir, "flowmanner.yaml"));
  assert.ok(yamlStat.isFile(), "flowmanner.yaml should be in cwd");

  // And no subdirectory was created.
  await assert.rejects(stat(join(dir, "x")));

  // The scaffolded yaml reflects the requested name.
  const yaml = await readFile(join(dir, "flowmanner.yaml"), "utf8");
  assert.match(yaml, /name: "?x"?/);

  await rm(dir, { recursive: true });
});

test("init refuses to scaffold into an existing folder when --here is not set", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdirSync } = await import("node:fs");
  const dir = await mkdtemp(join(tmpdir(), "fm-init-busy-"));
  const cliBin = join(import.meta.dirname, "..", "bin", "flowmanner.js");

  // Pre-create the target directory.
  mkdirSync(join(dir, "demo"));

  const result = spawnSync(
    "node",
    [cliBin, "init", "demo", "--template", "solo"],
    { cwd: dir, encoding: "utf8" },
  );
  assert.equal(result.status, 1, "init should refuse to scaffold into an existing folder");
  assert.match(result.stderr, /already exists/i);

  await rm(dir, { recursive: true });
});
