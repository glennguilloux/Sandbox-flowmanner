import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { apiRequest } from "../lib/api.js";
import type { RunSummary } from "../types.js";

export function registerAbortCommand(program: Command): void {
  program
    .command("abort <run-id>")
    .description("Abort a running execution")
    .option("--reason <reason>", "Reason string", "user_requested")
    .action(async (runId: string, opts: { reason: string }) => {
      const spinner = ora(`Aborting ${runId}…`).start();
      try {
        const run = await apiRequest<RunSummary>(
          `/api/v2/runs/${runId}/abort?reason=${encodeURIComponent(opts.reason)}`,
          { method: "POST" },
        );
        spinner.succeed(chalk.green(`Aborted (status=${run.status})`));
      } catch (err) {
        spinner.fail(chalk.red("Abort failed"));
        console.error(err);
        process.exitCode = 1;
      }
    });
}