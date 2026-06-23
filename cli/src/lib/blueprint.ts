/**
 * flowmanner.yaml <-> BlueprintCreate schema conversion.
 *
 * The local YAML uses a friendly shape with templated prompts. We
 * normalize it into the backend's BlueprintCreate / BlueprintDefinition
 * shape before pushing to /api/v2/blueprints.
 *
 * Keep this file dependency-light (just zod + js-yaml) so it can run
 * in `validate` without any network calls.
 */
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import yaml from "js-yaml";
import { z } from "zod";

// ── Local YAML schema ────────────────────────────────────────────────────

const NodeDefSchema = z.object({
  id: z.string().min(1),
  type: z.string().min(1),
  title: z.string().default(""),
  description: z.string().default(""),
  config: z.record(z.unknown()).default({}),
  dependencies: z.array(z.string()).default([]),
  assigned_model: z.string().nullable().optional(),
  assigned_agent_id: z.string().nullable().optional(),
  max_retries: z.number().int().nonnegative().default(3),
  fallback_strategy: z.string().default("human_escalate"),
});

const EdgeDefSchema = z.object({
  source: z.string().min(1),
  target: z.string().min(1),
  condition: z.string().nullable().optional(),
  label: z.string().nullable().optional(),
});

const BudgetDefSchema = z.object({
  max_cost_usd: z.number().nonnegative().default(10),
  max_wall_time_seconds: z.number().int().nonnegative().default(300),
  max_iterations: z.number().int().nonnegative().default(100),
  max_depth: z.number().int().nonnegative().default(5),
});

const BlueprintYmlSchema = z.object({
  version: z.literal(1).default(1),
  name: z.string().min(1),
  description: z.string().default(""),
  blueprint_type: z.enum([
    "solo",
    "dag",
    "swarm",
    "pipeline",
    "graph",
    "meta",
    "langgraph",
  ]).default("solo"),
  inputs: z.record(z.unknown()).default({}),
  outputs: z.record(z.unknown()).default({}),
  definition: z.object({
    blueprint_type: z.string().optional(),
    nodes: z.array(NodeDefSchema).default([]),
    edges: z.array(EdgeDefSchema).default([]),
    budget: BudgetDefSchema.default({}),
    config: z.record(z.unknown()).default({}),
  }),
});

export type BlueprintYml = z.infer<typeof BlueprintYmlSchema>;

// ── Backend payload ─────────────────────────────────────────────────────

/** Mirrors backend/app/schemas/blueprint.py:BlueprintCreate. */
export interface BlueprintCreatePayload {
  title: string;
  description: string;
  blueprint_type: string;
  definition: {
    blueprint_type: string;
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
    budget: Record<string, unknown>;
    config: Record<string, unknown>;
  };
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  tags?: string[];
  category?: string;
  icon?: string;
}

export interface LoadedBlueprint {
  /** Parsed YAML, normalized. */
  spec: BlueprintYml;
  /** Path the YAML was loaded from. */
  path: string;
  /** Server-ready payload. */
  payload: BlueprintCreatePayload;
}

/** Load + parse + normalize a flowmanner.yaml. Throws on schema errors. */
export async function loadBlueprintFile(
  path: string = "flowmanner.yaml",
): Promise<LoadedBlueprint> {
  const absPath = resolve(path);
  const text = await readFile(absPath, "utf8");
  const raw = yaml.load(text);
  const spec = BlueprintYmlSchema.parse(raw);

  const payload: BlueprintCreatePayload = {
    title: spec.name,
    description: spec.description,
    blueprint_type: spec.blueprint_type,
    definition: {
      blueprint_type: spec.definition.blueprint_type ?? spec.blueprint_type,
      nodes: spec.definition.nodes as unknown as Array<Record<string, unknown>>,
      edges: spec.definition.edges as unknown as Array<Record<string, unknown>>,
      budget: spec.definition.budget as unknown as Record<string, unknown>,
      config: spec.definition.config as unknown as Record<string, unknown>,
    },
    input_schema: Object.keys(spec.inputs).length > 0 ? spec.inputs : undefined,
    output_schema:
      Object.keys(spec.outputs).length > 0 ? spec.outputs : undefined,
  };
  return { spec, path: absPath, payload };
}

/** Walk up from cwd looking for the nearest flowmanner.yaml. */
export async function findBlueprintFile(
  start: string = process.cwd(),
): Promise<string | null> {
  const fs = await import("node:fs/promises");
  let dir = resolve(start);
  while (true) {
    const candidate = resolve(dir, "flowmanner.yaml");
    try {
      const stat = await fs.stat(candidate);
      if (stat.isFile()) return candidate;
    } catch {
      // not present, keep walking up
    }
    const parent = resolve(dir, "..");
    if (parent === dir) return null; // hit filesystem root
    dir = parent;
  }
}