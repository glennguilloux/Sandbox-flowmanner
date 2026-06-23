/**
 * `flowmanner run` — create a Run and tail its progress live.
 *
 * Flow:
 *   1. POST /api/v2/blueprints/{id}/run with input_data + budget_override
 *   2. Print the run id, then poll /api/v2/runs/{id} for status while
 *      streaming /api/v2/runs/{id}/events for live log lines.
 *
 * Output UX:
 *   - Top-line spinner shows status transitions (queued → executing → completed)
 *   - Below the spinner, a live log stream prints each substrate event
 *     as it arrives.
 *   - On terminal state (completed/failed/aborted), dump output_data /
 *     error_message and exit with the right code (0 / 1).
 */
import { Command } from "commander";
import chalk from "chalk";
import ora, { type Ora } from "ora";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { apiRequest, sseStream } from "../lib/api.js";
import type { RunEvent, RunSummary } from "../types.js";

interface RunOptions {
  blueprint?: string;
  input?: string[];
  budget?: string;
  noFollow?: boolean;
  json?: boolean;
}

export function registerRunCommand(program: Command): void {
  program
    .command("run [id]")
    .description("Execute a published Blueprint and stream live progress")
    .option("-b, --blueprint <id>", "Blueprint id (overrides .flowmanner/state.json)")
    .option(
      "-i, --input <kv...>",
      'Input values, e.g. --input topic="X" --input tone="casual"',
      [],
    )
    .option(
      "--budget <usd>",
      "Override max cost in USD (decimal)",
      (v) => Number(v),
    )
    .option("--no-follow", "Exit immediately after the run is created (no live tail)")
    .option("--json", "Emit the final run summary as JSON instead of formatted text")
    .action(async (idArg: string | undefined, opts: RunOptions) => {
      const blueprintId = opts.blueprint ?? idArg ?? (await readIdFromState());
      if (!blueprintId) {
        console.error(
          chalk.red(
            "No Blueprint id given. Pass one as an argument, " +
              "or run `flowmanner push` first.",
          ),
        );
        process.exitCode = 1;
        return;
      }

      const inputData = parseKvPairs(opts.input ?? []);
      const body: { input_data: Record<string, unknown>; budget_override?: unknown } = {
        input_data: inputData,
      };
      if (opts.budget !== undefined) {
        body.budget_override = { max_cost_usd: opts.budget };
      }

      let run: RunSummary;
      try {
        run = await apiRequest<RunSummary>(
          `/api/v2/blueprints/${blueprintId}/run`,
          { method: "POST", body },
        );
      } catch (err) {
        console.error(chalk.red("Failed to create run"));
        console.error(err);
        process.exitCode = 1;
        return;
      }

      if (opts.json) {
        console.log(JSON.stringify(run, null, 2));
      } else {
        console.log(chalk.dim(`run id: ${run.id}`));
        console.log(chalk.dim(`status: ${run.status}`));
      }

      if (opts.noFollow) return;

      await followRun(run.id, opts);
    });
}

async function followRun(runId: string, opts: RunOptions): Promise<void> {
  const spinner = ora({
    text: chalk.dim(`status: pending`),
    spinner: "dots",
  }).start();

  // Start tailing events concurrently with status polling. We use a
  // shared promise to coordinate shutdown.
  const tailPromise = tailEvents(runId, spinner, opts);

  let final: RunSummary | null = null;
  try {
    final = await pollUntilTerminal(runId, spinner);
  } catch (err) {
    spinner.fail(chalk.red("Lost connection while polling run status"));
    console.error(err);
    process.exitCode = 1;
    return;
  }

  await tailPromise;

  spinner.stop();
  if (opts.json) {
    console.log(JSON.stringify(final, null, 2));
  } else {
    printFinalSummary(final);
  }
  if (final.status === "completed") {
    process.exitCode = 0;
  } else if (final.status === "aborted") {
    process.exitCode = 130;
  } else {
    process.exitCode = 1;
  }
}

async function pollUntilTerminal(
  runId: string,
  spinner: Ora,
): Promise<RunSummary> {
  const terminal = new Set(["completed", "failed", "aborted"]);
  const interval = 1500;
  for (;;) {
    const run = await apiRequest<RunSummary>(`/api/v2/runs/${runId}`);
    if (!spinner.isSpinning) spinner.start();
    spinner.text = chalk.dim(
      `status: ${run.status}  ` +
        `tokens: ${run.total_tokens}  ` +
        `cost: $${run.total_cost_usd.toFixed(4)}`,
    );
    if (terminal.has(run.status)) return run;
    await sleep(interval);
  }
}

async function tailEvents(
  runId: string,
  spinner: Ora,
  opts: RunOptions,
): Promise<void> {
  try {
    for await (const evt of sseStream(`/api/v2/runs/${runId}/events`, {
      // Server supports ?from_sequence=&limit=; we start at 0 and
      // let the server filter new ones on keepalive.
      query: { from_sequence: 0, limit: 1000 },
    })) {
      if (opts.json) continue; // suppress human logs in --json mode
      const e = evt.data as RunEvent;
      const ts = e.timestamp ? chalk.dim(e.timestamp) : "";
      const actor = e.actor ? chalk.dim(`@${e.actor} `) : "";
      const seq = chalk.dim(`#${String(e.sequence).padStart(4, " ")}`);
      spinner.stop();
      console.log(`${ts} ${seq} ${actor}${chalk.cyan(e.type.padEnd(20))} ${formatPayload(e.payload)}`);
      spinner.start();
    }
  } catch (_err) { // eslint-disable-line @typescript-eslint/no-unused-vars -- stream errors are intentionally swallowed
    // Stream errors are non-fatal — polling keeps working. Just log.
    spinner.stop();
    console.log(chalk.dim("  (event stream closed)"));
    spinner.start();
  }
}

function formatPayload(payload: unknown): string {
  if (!payload) return "";
  if (typeof payload === "string") return payload;
  const s = JSON.stringify(payload);
  return s.length > 240 ? s.slice(0, 237) + "…" : s;
}

function printFinalSummary(run: RunSummary): void {
  console.log();
  if (run.status === "completed") {
    console.log(chalk.green.bold(`✔ Completed in ${formatDuration(run)}`));
    console.log(chalk.dim(`  tokens: ${run.total_tokens}  cost: $${run.total_cost_usd.toFixed(4)}`));
    if (run.output_data) {
      console.log();
      console.log(chalk.bold("Output:"));
      const text =
        typeof run.output_data.text === "string"
          ? run.output_data.text
          : JSON.stringify(run.output_data, null, 2);
      console.log(text);
    }
  } else if (run.status === "failed") {
    console.log(chalk.red.bold(`✗ Failed: ${run.error_message ?? "(no message)"}`));
  } else if (run.status === "aborted") {
    console.log(chalk.yellow.bold(`⏹ Aborted`));
  }
}

function formatDuration(run: RunSummary): string {
  if (!run.started_at || !run.completed_at) return "?";
  const ms =
    new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

function parseKvPairs(pairs: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const p of pairs) {
    const eq = p.indexOf("=");
    if (eq < 0) {
      console.error(
        chalk.yellow(`  ignoring --input "${p}" (expected key=value)`),
      );
      continue;
    }
    out[p.slice(0, eq)] = p.slice(eq + 1);
  }
  return out;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function readIdFromState(): Promise<string | null> {
  try {
    const raw = await readFile(
      resolve(process.cwd(), ".flowmanner/state.json"),
      "utf8",
    );
    const parsed = JSON.parse(raw) as { blueprint_id?: string };
    return parsed.blueprint_id ?? null;
  } catch {
    return null;
  }
}