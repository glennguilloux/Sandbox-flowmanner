/**
 * `flowmanner config` — view/edit persistent CLI settings.
 *
 * Subcommands:
 *   config get [key]            print a value (whole config if no key)
 *   config set <key> <value>    set a value
 *   config unset <key>          remove a value
 *   config path                 print where the config file lives
 */
import { Command } from "commander";
import chalk from "chalk";
import { getBaseUrl, getConfigPath, setBaseUrl } from "../lib/config.js";

const KNOWN_KEYS = new Set(["baseUrl", "email", "token", "workspaceId"]);

export function registerConfigCommand(program: Command): void {
  const cmd = program
    .command("config")
    .description("View or edit persistent CLI settings");

  cmd
    .command("get [key]")
    .description("Print one or all config values")
    .action((key?: string) => {
      if (!key) {
        console.log(chalk.dim(`baseUrl:  ${getBaseUrl()}`));
        console.log(chalk.dim(`config:   ${getConfigPath()}`));
        return;
      }
      if (!KNOWN_KEYS.has(key)) {
        console.error(
          chalk.red(
            `Unknown key "${key}". Known keys: ${[...KNOWN_KEYS].join(", ")}`,
          ),
        );
        process.exitCode = 1;
        return;
      }
      if (key === "baseUrl") {
        console.log(getBaseUrl());
      } else if (key === "token") {
        console.error(chalk.red("Refusing to print token to stdout."));
        process.exitCode = 1;
      } else {
        console.error(chalk.yellow(`Run \`flowmanner whoami\` for "${key}"`));
        process.exitCode = 1;
      }
    });

  cmd
    .command("set <key> <value>")
    .description("Set a config value")
    .action((key: string, value: string) => {
      if (!KNOWN_KEYS.has(key)) {
        console.error(
          chalk.red(
            `Unknown key "${key}". Known keys: ${[...KNOWN_KEYS].join(", ")}`,
          ),
        );
        process.exitCode = 1;
        return;
      }
      if (key === "baseUrl") setBaseUrl(value);
      else {
        console.error(
          chalk.red(
            `"${key}" is read-only or managed by another command.\n` +
              "  token/email: managed by `flowmanner login`",
          ),
        );
        process.exitCode = 1;
        return;
      }
      console.log(chalk.green(`${key} = ${value}`));
    });

  cmd
    .command("unset <key>")
    .description("Remove a config value")
    .action((_key: string) => {
      console.error(chalk.yellow("Use `flowmanner logout` to clear credentials."));
      process.exitCode = 1;
    });

  cmd
    .command("path")
    .description("Print the config file location")
    .action(() => {
      console.log(getConfigPath());
    });
}