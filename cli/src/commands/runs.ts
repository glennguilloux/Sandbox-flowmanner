import { Command } from "commander";
import chalk from "chalk";
import { apiRequest } from "../lib/api.js";
import type { PaginatedResponse, RunSummary } from "../types.js";

export function registerRunsCommand(program: Command): void {
  program
    .command("runs")
    .description("List your recent Runs")
    .option("--blueprint <id>", "Filter by Blueprint id")
    .option("--status <status>", "Filter by status")
    .option("--page <n>", "Page number", (v) => Number(v), 1)
    .option("--per-page <n>", "Items per page", (v) => Number(v), 20)
    .option("--json", "Output raw JSON")
    .action(
      async (opts: {
        blueprint?: string;
        status?: string;
        page: number;
        perPage: number;
        json?: boolean;
      }) => {
        const result = await apiRequest<PaginatedResponse<RunSummary>>(
          "/api/v2/runs/",
          {
            query: {
              blueprint_id: opts.blueprint,
              status: opts.status,
              page: opts.page,
              per_page: opts.perPage,
            },
          },
        );
        if (opts.json) {
          console.log(JSON.stringify(result, null, 2));
          return;
        }
        if (result.items.length === 0) {
          console.log(chalk.dim("No runs found."));
          return;
        }
        console.log(
          chalk.dim(
            `${result.items.length} of ${result.total} (page ${result.page}/${result.pages})`,
          ),
        );
        for (const r of result.items) {
          const id = r.id.slice(0, 8);
          const status = colorStatus(r.status);
          const cost = chalk.dim(`$${r.total_cost_usd.toFixed(4)}`);
          const blueprint = r.blueprint_id
            ? chalk.dim(r.blueprint_id.slice(0, 8))
            : chalk.dim("—");
          console.log(
            `  ${chalk.bold(id)}  ${status.padEnd(11)} cost=${cost}  bp=${blueprint}`,
          );
        }
      },
    );
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