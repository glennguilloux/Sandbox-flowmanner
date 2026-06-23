import { Command } from "commander";
import chalk from "chalk";
import { clearCredentials } from "../lib/config.js";

export function registerLogoutCommand(program: Command): void {
  program
    .command("logout")
    .description("Remove stored credentials")
    .action(() => {
      clearCredentials();
      console.log(chalk.green("Logged out."));
    });
}