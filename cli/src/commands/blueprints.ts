import { Command } from "commander";
import chalk from "chalk";
import { apiRequest } from "../lib/api.js";
import type { BlueprintSummary, PaginatedResponse } from "../types.js";

export function registerBlueprintsCommand(program: Command): void {
  program
    .command("blueprints")
    .alias("bp")
    .description("List your Blueprints")
    .option("--type <type>", "Filter by blueprint_type")
    .option("--status <status>", "Filter by status (draft|published|deprecated)")
    .option("--page <n>", "Page number", (v) => Number(v), 1)
    .option("--per-page <n>", "Items per page", (v) => Number(v), 20)
    .option("--json", "Output raw JSON")
    .action(
      async (opts: {
        type?: string;
        status?: string;
        page: number;
        perPage: number;
        json?: boolean;
      }) => {
        const result = await apiRequest<PaginatedResponse<BlueprintSummary>>(
          "/api/v2/blueprints/",
          {
            query: {
              blueprint_type: opts.type,
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
          console.log(chalk.dim("No blueprints found."));
          return;
        }
        console.log(
          chalk.dim(
            `${result.items.length} of ${result.total} (page ${result.page}/${result.pages})`,
          ),
        );
        for (const bp of result.items) {
          const id = bp.id.slice(0, 8);
          const status = colorStatus(bp.status);
          const type = chalk.dim(bp.blueprint_type.padEnd(9));
          const title = bp.title;
          console.log(`  ${chalk.bold(id)}  ${type} ${status.padEnd(11)} ${title}`);
        }
      },
    );
}

function colorStatus(s: string): string {
  switch (s) {
    case "draft":
      return chalk.yellow(s);
    case "published":
      return chalk.green(s);
    case "deprecated":
      return chalk.gray(s);
    default:
      return s;
  }
}