/**
 * `flowmanner login` — exchange email + password for a JWT, store it.
 *
 * Flow:
 *   1. Prompt for email + password (hidden input via inquirer).
 *   2. POST /api/v2/auth/login — get access_token.
 *   3. GET /api/v2/auth/me — fetch user (also warms the credentials file
 *      with workspace_id if available).
 *   4. Save to ~/.flowmanner/config.json (via lib/config).
 *
 * Two-factor auth (TOTP) is handled by the backend — see v2/auth.py.
 * When the account has 2FA enabled, login returns
 * `{ requires_2fa: true, temp_token }` instead of a real access_token.
 * In that case we prompt for the TOTP code and call /auth/login/2fa.
 */
import { Command } from "commander";
import chalk from "chalk";
import inquirer from "inquirer";
import ora from "ora";
import { apiRequest, FlowmannerApiError } from "../lib/api.js";
import { saveCredentials } from "../lib/config.js";
import type { AuthTokens, UserSummary } from "../types.js";

interface LoginResponse {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
  requires_2fa?: boolean;
  temp_token?: string;
}

export function registerLoginCommand(program: Command): void {
  program
    .command("login")
    .description("Authenticate with FlowManner and store credentials")
    .option("--email <email>", "Email address (skip the prompt)")
    .option("--password <password>", "Password (skip the prompt; less secure)")
    .option("--base-url <url>", "Override the FlowManner base URL")
    .action(async (opts: { email?: string; password?: string; baseUrl?: string }) => {
      const { setBaseUrl } = await import("../lib/config.js");
      if (opts.baseUrl) setBaseUrl(opts.baseUrl);

      const answers = await inquirer.prompt<{ email: string; password: string }>([
        {
          type: "input",
          name: "email",
          message: "Email:",
          default: opts.email,
          validate: (v: string) => (v.includes("@") ? true : "Enter a valid email"),
        },
        {
          type: "password",
          name: "password",
          message: "Password:",
          mask: "*",
          default: opts.password,
        },
      ]);

      const spinner = ora("Logging in…").start();
      let accessToken: string;
      let email = answers.email;

      try {
        const resp = await apiRequest<LoginResponse>("/api/v2/auth/login", {
          method: "POST",
          body: { email: answers.email, password: answers.password },
          auth: false,
        });

        if (resp.requires_2fa) {
          spinner.text = "Two-factor code required";
          const { totp } = await inquirer.prompt<{ totp: string }>([
            {
              type: "input",
              name: "totp",
              message: "TOTP code:",
              validate: (v: string) =>
                /^\d{6}$/.test(v) ? true : "Six-digit code required",
            },
          ]);
          const twoFa = await apiRequest<AuthTokens>(
            "/api/v2/auth/login/2fa",
            {
              method: "POST",
              body: { temp_token: resp.temp_token, code: totp },
              auth: false,
            },
          );
          accessToken = twoFa.access_token;
        } else {
          accessToken = resp.access_token;
        }

        // Fetch the user record so we can stash workspace_id.
        const meResp = await fetchMe(accessToken);
        email = meResp?.email ?? email;

        saveCredentials({
          token: accessToken,
          email,
          workspaceId: meResp?.workspace_id ?? undefined,
        });
        spinner.succeed(chalk.green(`Logged in as ${email}`));
      } catch (err) {
        spinner.fail(chalk.red("Login failed"));
        if (err instanceof FlowmannerApiError) {
          console.error(chalk.red(`  ${err.code}: ${err.message}`));
          if (err.code === "INVALID_CREDENTIALS") {
            console.error(chalk.dim("  Double-check email and password."));
          }
        } else {
          console.error(err);
        }
        process.exitCode = 1;
      }
    });
}

async function fetchMe(token: string): Promise<UserSummary | null> {
  const { getBaseUrl } = await import("../lib/config.js");
  const resp = await fetch(`${getBaseUrl()}/api/v2/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) return null;
  const env = (await resp.json()) as { data: UserSummary };
  return env.data;
}