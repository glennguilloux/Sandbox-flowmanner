import { Command } from "commander";
import chalk from "chalk";
import { apiRequest } from "../lib/api.js";
import type { RunSummary } from "../types.js";

export function registerStatusCommand(program: Command): void {
  program
    .command("status <run-id>")
    .description("Show current status of a single run")
    .option("--json", "Output raw JSON")
    .action(async (runId: string, opts: { json?: boolean }) => {
      const run = await apiRequest<RunSummary>(`/api/v2/runs/${runId}`);
      if (opts.json) {
        console.log(JSON.stringify(run, null, 2));
        return;
      }
      const status = colorStatus(run.status);
      console.log(`${chalk.bold(run.id)}  ${status}`);
      console.log(chalk.dim(`  blueprint:  ${run.blueprint_id ?? "—"}`));
      console.log(chalk.dim(`  created:    ${run.created_at ?? "—"}`));
      console.log(chalk.dim(`  started:    ${run.started_at ?? "—"}`));
      console.log(chalk.dim(`  completed:  ${run.completed_at ?? "—"}`));
      console.log(chalk.dim(`  tokens:     ${run.total_tokens}`));
      console.log(chalk.dim(`  cost:       $${run.total_cost_usd.toFixed(4)}`));
      if (run.budget_limit_usd != null) {
        console.log(chalk.dim(`  budget:     $${run.budget_limit_usd.toFixed(2)}`));
      }
      if (run.error_message) {
        console.log();
        console.log(chalk.red(`  error: ${run.error_message}`));
      }
      if (run.output_data) {
        console.log();
        console.log(chalk.bold("Output:"));
        const text =
          typeof run.output_data.text === "string"
            ? run.output_data.text
            : JSON.stringify(run.output_data, null, 2);
        console.log(text);
      }
    });
}

function colorStatus(s: string): string {
  switch (s) {
    case "completed":
      return chalk.green(s);
    case "executing":
    case "queued":
      return chalk.cyan(s);
    case "failed":
      return chalk.red(s);
    case "aborted":
      return chalk.yellow(s);
    case "pending":
      return chalk.dim(s);
    case "paused":
      return chalk.magenta(s);
    default:
      return s;
  }
}