/**
 * `flowmanner init <name>` — scaffold a new workflow project.
 *
 * Creates a folder with:
 *   flowmanner.yaml         — the workflow definition
 *   README.md               — quick-start instructions
 *   .gitignore              — sensible defaults
 *   .flowmanner/            — local project state (cached ids)
 */
import { Command } from "commander";
import chalk from "chalk";
import { mkdir, writeFile, access, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Resolve the templates directory. Works in both `tsx` (dev, from src/)
 * and `node` (built, from dist/) — see the build script which copies
 * templates/ alongside dist/.
 */
function resolveTemplatesDir(): string {
  // Production: dist/commands/init.js → ../../templates
  const productionCandidate = resolve(__dirname, "../../templates");
  // Dev / tsx: src/commands/init.ts → ../lib/templates
  const devCandidate = resolve(__dirname, "../lib/templates");
  if (existsSync(productionCandidate)) return productionCandidate;
  if (existsSync(devCandidate)) return devCandidate;
  return productionCandidate; // will fail loud below — better than silent
}

export function registerInitCommand(program: Command): void {
  program
    .command("init <name>")
    .description("Scaffold a new workflow project in ./<name>/")
    .option("-t, --template <name>", "Template to use (default: solo)", "solo")
    .option("--here", "Initialize in current directory instead of a new folder")
    .action(async (name: string, opts: { template: string; here?: boolean }) => {
      const targetDir = opts.here ? process.cwd() : resolve(process.cwd(), name);

      // The existence check only applies when we're scaffolding into a
      // NEW subdirectory. With --here the target is the current cwd,
      // which always exists — checking would always reject.
      if (!opts.here) {
        try {
          await access(targetDir);
          // Directory exists — refuse unless --force is added (not yet).
          console.error(
            chalk.red(
              `Directory already exists: ${targetDir}\n` +
                `  Re-run with a new name, or remove it first.`,
            ),
          );
          process.exitCode = 1;
          return;
        } catch {
          // good — doesn't exist yet
        }
      }

      if (!opts.here) await mkdir(targetDir, { recursive: true });

      const templateFile = join(resolveTemplatesDir(), `${opts.template}.yaml`);
      const destFile = join(targetDir, "flowmanner.yaml");
      let templateText: string;
      try {
        templateText = await readFile(templateFile, "utf8");
      } catch {
        console.error(
          chalk.red(`Template "${opts.template}" not found at ${templateFile}`),
        );
        process.exitCode = 1;
        return;
      }
      // Replace the {{name}} placeholder so the scaffolded workflow
      // matches the project name the user asked for.
      templateText = templateText.replace(/\{\{\s*name\s*\}\}/g, name);
      await writeFile(destFile, templateText);

      await writeFile(
        join(targetDir, ".gitignore"),
        `.flowmanner/\nnode_modules/\n*.log\n`,
      );

      await writeFile(
        join(targetDir, "README.md"),
        `# ${name}

A FlowManner workflow.

## Quick start

\`\`\`bash
flowmanner login        # one-time
flowmanner validate     # check flowmanner.yaml locally
flowmanner push         # create a draft Blueprint on FlowManner
flowmanner publish      # mark it ready to run
flowmanner run          # execute + stream live progress
\`\`\`

## Anatomy of flowmanner.yaml

| Key | Purpose |
|-----|---------|
| \`name\` | Human-friendly title (also becomes the Blueprint title) |
| \`blueprint_type\` | solo / dag / swarm / pipeline / graph / meta / langgraph |
| \`inputs\` | Variables available as \`{{ inputs.<key> }}\` in prompts |
| \`definition.nodes\` | The actual work (one node per LLM call / tool / etc.) |
| \`definition.edges\` | Directed links between nodes (empty for solo) |
| \`definition.budget\` | max_cost_usd / max_wall_time_seconds / max_iterations / max_depth |

See \`flowmanner run --help\` for how to pass inputs at invoke time.
`,
      );

      await mkdir(join(targetDir, ".flowmanner"), { recursive: true });
      await writeFile(
        join(targetDir, ".flowmanner/.gitkeep"),
        `# Local CLI state — last pushed Blueprint ID, run cache, etc.`,
      );

      console.log(chalk.green(`✔ Initialized workflow in ${targetDir}`));
      console.log();
      console.log("Next steps:");
      console.log(chalk.cyan(`  cd ${opts.here ? "." : name}`));
      console.log(chalk.cyan("  flowmanner validate"));
      console.log(chalk.cyan("  flowmanner push"));
      console.log(chalk.cyan("  flowmanner publish"));
      console.log(chalk.cyan(`  flowmanner run --input topic='Your topic'`));
    });
}
