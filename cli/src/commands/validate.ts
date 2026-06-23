import { Command } from "commander";
import chalk from "chalk";
import { loadBlueprintFile } from "../lib/blueprint.js";

export function registerValidateCommand(program: Command): void {
  program
    .command("validate [path]")
    .description("Parse and check a flowmanner.yaml locally")
    .action(async (path: string = "flowmanner.yaml") => {
      try {
        const { spec, payload } = await loadBlueprintFile(path);
        console.log(chalk.green(`✔ ${path} is valid`));
        console.log(chalk.dim(`  name:           ${spec.name}`));
        console.log(chalk.dim(`  blueprint_type: ${spec.blueprint_type}`));
        console.log(chalk.dim(`  nodes:          ${payload.definition.nodes.length}`));
        console.log(chalk.dim(`  edges:          ${payload.definition.edges.length}`));
        if (payload.input_schema) {
          console.log(
            chalk.dim(
              `  inputs:         ${Object.keys(payload.input_schema).join(", ")}`,
            ),
          );
        }
      } catch (err) {
        console.error(chalk.red(`✗ ${path} failed validation`));
        if (err instanceof Error) console.error(chalk.dim(`  ${err.message}`));
        process.exitCode = 1;
      }
    });
}