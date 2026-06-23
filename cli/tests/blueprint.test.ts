/**
 * Tests for src/lib/blueprint.ts — YAML parsing + schema validation +
 * normalization into the BlueprintCreate shape the backend expects.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { writeFile, mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

test("parses a minimal solo flowmanner.yaml", async () => {
  const dir = await mkdtemp(join(tmpdir(), "fm-blueprint-"));
  const file = join(dir, "flowmanner.yaml");
  await writeFile(
    file,
    `
version: 1
name: hello
blueprint_type: solo
inputs:
  topic:
    type: string
    default: "world"
definition:
  nodes:
    - id: greet
      type: llm
      config:
        prompt: "Say hi to {{ inputs.topic }}"
  edges: []
  budget:
    max_cost_usd: 0.50
`,
  );

  const { loadBlueprintFile } = await import("../src/lib/blueprint.js");
  const result = await loadBlueprintFile(file);

  assert.equal(result.spec.name, "hello");
  assert.equal(result.spec.blueprint_type, "solo");
  assert.equal(result.payload.title, "hello");
  assert.equal(result.payload.definition.nodes.length, 1);
  assert.equal(result.payload.definition.nodes[0]?.id, "greet");
  assert.equal(result.payload.input_schema?.["topic"]?.["type"], "string");
  await rm(dir, { recursive: true });
});

test("rejects missing required fields", async () => {
  const dir = await mkdtemp(join(tmpdir(), "fm-blueprint-"));
  const file = join(dir, "flowmanner.yaml");
  await writeFile(file, "blueprint_type: solo\n");

  const { loadBlueprintFile } = await import("../src/lib/blueprint.js");
  await assert.rejects(loadBlueprintFile(file), (err: unknown) => {
    assert.ok(err instanceof Error);
    assert.match(err.message, /name/);
    return true;
  });
  await rm(dir, { recursive: true });
});

test("rejects unknown blueprint_type", async () => {
  const dir = await mkdtemp(join(tmpdir(), "fm-blueprint-"));
  const file = join(dir, "flowmanner.yaml");
  await writeFile(
    file,
    `
version: 1
name: bad
blueprint_type: not-a-real-type
definition:
  nodes: []
  edges: []
`,
  );
  const { loadBlueprintFile } = await import("../src/lib/blueprint.js");
  await assert.rejects(loadBlueprintFile(file), (err: unknown) => {
    assert.ok(err instanceof Error);
    return true;
  });
  await rm(dir, { recursive: true });
});

test("defaults to solo when blueprint_type is omitted", async () => {
  const dir = await mkdtemp(join(tmpdir(), "fm-blueprint-"));
  const file = join(dir, "flowmanner.yaml");
  await writeFile(
    file,
    `
name: minimal
definition:
  nodes: []
  edges: []
`,
  );
  const { loadBlueprintFile } = await import("../src/lib/blueprint.js");
  const result = await loadBlueprintFile(file);
  assert.equal(result.spec.blueprint_type, "solo");
  assert.equal(result.payload.blueprint_type, "solo");
  await rm(dir, { recursive: true });
});