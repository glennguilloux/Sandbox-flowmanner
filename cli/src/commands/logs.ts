import { Command } from "commander";
import chalk from "chalk";
import { apiRequest, sseStream } from "../lib/api.js";
import type { RunEvent } from "../types.js";

export function registerLogsCommand(program: Command): void {
  program
    .command("logs <run-id>")
    .description("Print event log for a run (use --follow to live-tail)")
    .option("-f, --follow", "Stream live events via SSE instead of dumping history")
    .option("--from <seq>", "Start from event sequence number", (v) => Number(v), 0)
    .option("--limit <n>", "Max events to fetch", (v) => Number(v), 200)
    .option("--json", "Output raw JSON events")
    .action(
      async (
        runId: string,
        opts: { follow?: boolean; from: number; limit: number; json?: boolean },
      ) => {
        if (opts.follow) {
          for await (const evt of sseStream(`/api/v2/runs/${runId}/events`, {
            query: { from_sequence: opts.from, limit: opts.limit },
          })) {
            if (opts.json) {
              console.log(JSON.stringify(evt.data));
            } else {
              const e = evt.data as RunEvent;
              const ts = e.timestamp ? chalk.dim(e.timestamp) : "";
              const actor = e.actor ? chalk.dim(`@${e.actor} `) : "";
              console.log(
                `${ts} ${chalk.dim(`#${String(e.sequence).padStart(4)}`)} ${actor}${chalk.cyan(e.type.padEnd(20))}`,
              );
            }
          }
          return;
        }

        // Non-follow: single batched fetch.
        const resp = await apiRequest<{
          run_id: string;
          events: RunEvent[];
          count: number;
        }>(`/api/v2/runs/${runId}/events`, {
          query: { from_sequence: opts.from, limit: opts.limit },
        });
        if (opts.json) {
          console.log(JSON.stringify(resp, null, 2));
          return;
        }
        console.log(chalk.dim(`${resp.count} events for ${runId}`));
        for (const e of resp.events) {
          const ts = e.timestamp ? chalk.dim(e.timestamp) : "";
          const actor = e.actor ? chalk.dim(`@${e.actor} `) : "";
          console.log(
            `${ts} ${chalk.dim(`#${String(e.sequence).padStart(4)}`)} ${actor}${chalk.cyan(e.type.padEnd(20))}`,
          );
        }
      },
    );
}
