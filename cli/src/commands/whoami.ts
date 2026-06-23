import { Command } from "commander";
import chalk from "chalk";
import { apiRequest, NotAuthenticatedError } from "../lib/api.js";
import type { UserSummary } from "../types.js";

export function registerWhoamiCommand(program: Command): void {
  program
    .command("whoami")
    .description("Print the currently logged-in user")
    .action(async () => {
      try {
        const me = await apiRequest<UserSummary>("/api/v2/auth/me");
        console.log(chalk.bold(me.email));
        if (me.full_name) console.log(chalk.dim(me.full_name));
        console.log(chalk.dim(`user_id: ${me.id}`));
        if (me.workspace_id)
          console.log(chalk.dim(`workspace_id: ${me.workspace_id}`));
      } catch (err) {
        if (err instanceof NotAuthenticatedError) {
          console.error(chalk.red("Not logged in. Run `flowmanner login`."));
        } else {
          throw err;
        }
        process.exitCode = 1;
      }
    });
}
