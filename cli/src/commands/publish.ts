import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { apiRequest } from "../lib/api.js";
import type { BlueprintSummary } from "../types.js";

export function registerPublishCommand(program: Command): void {
  program
    .command("publish [id]")
    .description(
      "Mark a draft Blueprint as published (required before it can be run)",
    )
    .action(async (idArg?: string) => {
      const id = idArg ?? (await readIdFromState());
      if (!id) {
        console.error(
          chalk.red(
            "No Blueprint id given and none found in .flowmanner/state.json.\n" +
              "  Run `flowmanner push` first, or pass the id as an argument.",
          ),
        );
        process.exitCode = 1;
        return;
      }
      const spinner = ora(`Publishing ${id}…`).start();
      try {
        const result = await apiRequest<BlueprintSummary>(
          `/api/v2/blueprints/${id}/publish`,
          { method: "POST" },
        );
        spinner.succeed(chalk.green(`Published ${result.title} v${result.version}`));
      } catch (err) {
        spinner.fail(chalk.red("Publish failed"));
        console.error(err);
        process.exitCode = 1;
      }
    });
}

async function readIdFromState(): Promise<string | null> {
  try {
    const path = resolve(process.cwd(), ".flowmanner/state.json");
    const raw = await readFile(path, "utf8");
    const parsed = JSON.parse(raw) as { blueprint_id?: string };
    return parsed.blueprint_id ?? null;
  } catch {
    return null;
  }
}