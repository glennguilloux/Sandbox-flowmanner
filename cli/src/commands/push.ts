import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { writeFile, mkdir } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { loadBlueprintFile } from "../lib/blueprint.js";
import { apiRequest } from "../lib/api.js";
import type { BlueprintSummary } from "../types.js";

export function registerPushCommand(program: Command): void {
  program
    .command("push")
    .description("Create or update a Blueprint from ./flowmanner.yaml")
    .option("-f, --file <path>", "Path to flowmanner.yaml", "flowmanner.yaml")
    .option(
      "--update <id>",
      "Update an existing Blueprint instead of creating a new one",
    )
    .action(
      async (opts: { file: string; update?: string }) => {
        const spinner = ora("Reading workflow…").start();
        let loaded;
        try {
          loaded = await loadBlueprintFile(opts.file);
        } catch (err) {
          spinner.fail(chalk.red("Failed to read workflow"));
          console.error(chalk.dim(`  ${(err as Error).message}`));
          process.exitCode = 1;
          return;
        }
        spinner.succeed(`Read ${loaded.spec.name}`);

        const pushSpinner = ora(
          opts.update ? `Updating ${opts.update}…` : "Creating Blueprint…",
        ).start();
        try {
          let result: BlueprintSummary;
          if (opts.update) {
            result = await apiRequest<BlueprintSummary>(
              `/api/v2/blueprints/${opts.update}`,
              {
                method: "PATCH",
                body: {
                  title: loaded.payload.title,
                  description: loaded.payload.description,
                  definition: loaded.payload.definition,
                  input_schema: loaded.payload.input_schema,
                  output_schema: loaded.payload.output_schema,
                },
              },
            );
          } else {
            result = await apiRequest<BlueprintSummary>("/api/v2/blueprints/", {
              method: "POST",
              body: loaded.payload,
            });
          }
          pushSpinner.succeed(
            chalk.green(
              `${opts.update ? "Updated" : "Created"} Blueprint ${result.id}`,
            ),
          );

          // Cache the id so subsequent `publish` / `run` don't need it.
          const stateDir = resolve(dirname(loaded.path), ".flowmanner");
          await mkdir(stateDir, { recursive: true });
          await writeFile(
            resolve(stateDir, "state.json"),
            JSON.stringify(
              { blueprint_id: result.id, version: result.version, status: result.status },
              null,
              2,
            ),
          );
          console.log(chalk.dim(`  Saved id to .flowmanner/state.json`));
          if (result.status === "draft") {
            console.log();
            console.log("Next:");
            console.log(chalk.cyan("  flowmanner publish"));
          }
        } catch (err) {
          pushSpinner.fail(chalk.red("Push failed"));
          console.error(err);
          process.exitCode = 1;
        }
      },
    );
}