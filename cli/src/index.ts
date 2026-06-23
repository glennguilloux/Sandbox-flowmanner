/**
 * CLI entry point. Wires up commander with all subcommands.
 *
 * The help text intentionally leads with the most common dev loop:
 *   login → init → push → publish → run
 * so first-time users see the happy path immediately.
 */
import { Command } from "commander";
import chalk from "chalk";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { registerLoginCommand } from "./commands/login.js";
import { registerLogoutCommand } from "./commands/logout.js";
import { registerWhoamiCommand } from "./commands/whoami.js";
import { registerInitCommand } from "./commands/init.js";
import { registerValidateCommand } from "./commands/validate.js";
import { registerPushCommand } from "./commands/push.js";
import { registerPublishCommand } from "./commands/publish.js";
import { registerRunCommand } from "./commands/run.js";
import { registerBlueprintsCommand } from "./commands/blueprints.js";
import { registerRunsCommand } from "./commands/runs.js";
import { registerLogsCommand } from "./commands/logs.js";
import { registerStatusCommand } from "./commands/status.js";
import { registerAbortCommand } from "./commands/abort.js";
import { registerConfigCommand } from "./commands/config.js";
import {
  FlowmannerApiError,
  NotAuthenticatedError,
} from "./lib/api.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const pkgPath = resolve(__dirname, "../package.json");
const pkg = JSON.parse(readFileSync(pkgPath, "utf8")) as {
  name: string;
  version: string;
  description: string;
};

const program = new Command();

program
  .name("flowmanner")
  .description(pkg.description)
  .version(pkg.version)
  .addHelpText(
    "after",
    `
${chalk.bold("Quick start:")}
  ${chalk.cyan("flowmanner login")}                  ${chalk.dim("# authenticate")}
  ${chalk.cyan("flowmanner init my-first-workflow")} ${chalk.dim("# scaffold a project")}
  ${chalk.cyan("flowmanner validate")}               ${chalk.dim("# check flowmanner.yaml")}
  ${chalk.cyan("flowmanner push")}                   ${chalk.dim("# create the Blueprint")}
  ${chalk.cyan("flowmanner publish")}                ${chalk.dim("# mark it ready to run")}
  ${chalk.cyan("flowmanner run")}                    ${chalk.dim("# execute + stream live progress")}

${chalk.bold("Docs:")}  https://flowmanner.com/documentation
`,
  );

registerLoginCommand(program);
registerLogoutCommand(program);
registerWhoamiCommand(program);
registerInitCommand(program);
registerValidateCommand(program);
registerPushCommand(program);
registerPublishCommand(program);
registerRunCommand(program);
registerBlueprintsCommand(program);
registerRunsCommand(program);
registerLogsCommand(program);
registerStatusCommand(program);
registerAbortCommand(program);
registerConfigCommand(program);

program.parseAsync(process.argv).catch((err: unknown) => {
  // Surface unhandled errors cleanly rather than dumping a stack
  // trace that obscures the actual problem.
  if (err instanceof NotAuthenticatedError) {
    console.error(chalk.red(err.message));
    process.exitCode = 1;
    return;
  }
  if (err instanceof FlowmannerApiError) {
    console.error(chalk.red(`${err.code}: ${err.message}`));
    if (err.details) {
      console.error(chalk.dim(`  ${JSON.stringify(err.details)}`));
    }
    process.exitCode = 1;
    return;
  }
  console.error(chalk.red("Unexpected error:"));
  if (err instanceof Error) {
    console.error(chalk.dim(`  ${err.message}`));
    if (process.env["DEBUG"]) console.error(err.stack);
  } else {
    console.error(err);
  }
  process.exitCode = 1;
});