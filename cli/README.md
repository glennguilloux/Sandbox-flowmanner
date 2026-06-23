# @flowmanner/cli

Official FlowManner CLI — author, push, and run AI workflows from your
terminal. Talks to the FlowManner v2 API as a thin client. All workflow
execution happens server-side; the CLI is the local authoring and
orchestration layer.

> Status: **v0.1.0** — single template (`solo`), single auth mode
> (email + password → JWT). See [Roadmap](#roadmap) for what's next.

---

## Install

```bash
npm install -g @flowmanner/cli
```

Once installed, the `flowmanner` command is on your `$PATH`.

## Quick start

The three commands the docs promise:

```bash
npm install -g @flowmanner/cli
flowmanner login
flowmanner init my-first-workflow
```

`flowmanner init` creates a new folder with a `flowmanner.yaml`,
`README.md`, `.gitignore`, and `.flowmanner/`. The default template
is a single-step LLM call (`solo`) so you can push and run a real
workflow within a minute.

```bash
cd my-first-workflow
flowmanner validate                 # local schema check
flowmanner push                     # POST /api/v2/blueprints/
flowmanner publish                  # mark it ready to run
flowmanner run                      # execute + stream live progress
```

The `push` command writes the new Blueprint id to
`.flowmanner/state.json`, so subsequent `publish` / `run` invocations
don't need to specify the id.

---

## Commands

| Command | Description |
|---------|-------------|
| `flowmanner login` | Authenticate (email + password, with optional 2FA) |
| `flowmanner logout` | Remove stored credentials |
| `flowmanner whoami` | Print the currently logged-in user |
| `flowmanner init <name>` | Scaffold a new workflow project |
| `flowmanner validate [path]` | Parse + schema-check `flowmanner.yaml` |
| `flowmanner push` | Create or update a Blueprint |
| `flowmanner publish [id]` | Mark a draft as runnable |
| `flowmanner run [id]` | Execute a Blueprint, stream live progress |
| `flowmanner blueprints` (alias `bp`) | List Blueprints |
| `flowmanner runs` | List Runs |
| `flowmanner logs <run-id>` | Show event log (`--follow` to live-tail) |
| `flowmanner status <run-id>` | Show current state of a single Run |
| `flowmanner abort <run-id>` | Abort a running execution |
| `flowmanner config get\|set\|path` | Manage CLI settings |

Every list / get command accepts `--json` for machine-readable output,
suitable for piping into `jq` or shell scripts.

---

## Authentication

`flowmanner login` prompts for email + password, exchanges them for a
JWT at `POST /api/v2/auth/login`, and stores the token at
`~/.flowmanner/config.json`. If your account has 2FA enabled, the CLI
prompts for the TOTP code and calls `/api/v2/auth/login/2fa` to
upgrade the temporary token to a real one.

The token is sent as `Authorization: Bearer *** on every API call.
The config file inherits the operating system's standard
permissions (0600 on Unix). Override the location with
`FLOWMANNER_CONFIG_DIR=/some/path flowmanner login`.

When the JWT expires, you'll see `401 UNAUTHORIZED`. Run
`flowmanner login` again to refresh.

---

## `flowmanner.yaml` reference

```yaml
version: 1                              # always 1 today
name: my-first-workflow                 # Blueprint title
description: ...                        # shown in listings
blueprint_type: solo                    # solo | dag | swarm | pipeline | graph | meta | langgraph

inputs:                                 # variables available as {{ inputs.<key> }}
  topic:
    type: string
    default: "AI agent reliability"

outputs: {}                             # optional response schema

definition:                             # the workflow itself
  blueprint_type: solo
  nodes:
    - id: draft
      type: llm
      title: Draft the brief
      config:
        prompt: "Write a 3-paragraph brief about {{ inputs.topic }}."
        model: gpt-4o-mini
        max_tokens: 800
      assigned_model: gpt-4o-mini
  edges: []
  budget:
    max_cost_usd: 1.00
    max_wall_time_seconds: 120
    max_iterations: 5
    max_depth: 1
  config: {}
```

This shape mirrors the backend's `BlueprintCreate` schema in
`backend/app/schemas/blueprint.py` and is pushed verbatim to
`POST /api/v2/blueprints/`. The CLI normalizes the friendly YAML
into the JSONB form the backend stores.

---

## Calling `flowmanner run`

```bash
flowmanner run --input topic="RAG for code" --input tone="playful"
flowmanner run --budget 0.50            # cap spend at $0.50
flowmanner run --no-follow              # exit immediately after the run is created
flowmanner run --json                   # emit final RunSummary as JSON
```

`flowmanner run` does two things concurrently:

1. **Polls** `/api/v2/runs/{id}` every 1.5s and updates the spinner.
2. **Streams** `/api/v2/runs/{id}/events` over SSE and prints each
   substrate event as it arrives.

On terminal state, the spinner stops, a summary prints (tokens,
cost, duration), and the exit code reflects the outcome (0 =
completed, 1 = failed, 130 = aborted). Use `--no-follow` in CI to
just create the run and walk away.

---

## Project layout

This is a separate npm package; it does not share code with the
backend repo. The directory under `flowmanner/cli/` is the source
of truth — when we're ready to publish, we move it to its own repo
and `npm publish` from CI.

```
cli/
├── bin/flowmanner.js          # shebang entry; imports dist/index.js
├── src/
│   ├── index.ts               # CLI root, wires commander subcommands
│   ├── types.ts               # BlueprintSummary, RunSummary, etc.
│   ├── commands/
│   │   ├── login.ts           # email + password → JWT
│   │   ├── logout.ts
│   │   ├── whoami.ts
│   │   ├── init.ts            # scaffold from a template
│   │   ├── validate.ts        # local YAML schema check
│   │   ├── push.ts            # POST /api/v2/blueprints/
│   │   ├── publish.ts         # POST /api/v2/blueprints/{id}/publish
│   │   ├── run.ts             # POST /run + live progress tail
│   │   ├── blueprints.ts      # GET /blueprints/  (alias: bp)
│   │   ├── runs.ts            # GET /runs/
│   │   ├── logs.ts            # GET /runs/{id}/events  (or SSE)
│   │   ├── status.ts          # GET /runs/{id}
│   │   ├── abort.ts           # POST /runs/{id}/abort
│   │   └── config.ts          # get / set / path
│   └── lib/
│       ├── api.ts             # fetch wrapper, envelope unwrap, SSE parser
│       ├── config.ts          # persistent state via `conf`
│       ├── blueprint.ts       # YAML → BlueprintCreate schema (zod)
│       └── templates/
│           └── solo.yaml      # default `init` template
├── templates/                 # copied here by `npm run build`
├── package.json
├── tsconfig.json
└── .gitignore
```

---

## How it talks to FlowManner

Every command goes through `src/lib/api.ts`, which:

- Attaches `Authorization: Bearer *** from `~/.flowmanner/config.json`
- Unwraps the v2 envelope (`{ data, meta, error }`) so callers see
  just the payload
- Surfaces v2 error envelopes as `FlowmannerApiError` with code,
  message, and details
- Provides `sseStream()` for the run-events endpoint

All v2 endpoints follow the envelope convention described in
`backend/app/api/v2/base.py`. The CLI is intentionally dumb about
that — it doesn't try to be clever, just unwraps `data` and surfaces
`error`.

---

## State files

| Path | Owner | Contents |
|------|-------|----------|
| `~/.flowmanner/config.json` | `flowmanner login` / `config` | JWT, email, base URL, workspace id |
| `./.flowmanner/state.json` | `flowmanner push` | Last pushed Blueprint id + version |

The home-directory config is created on first login. The
project-local state is created on first push.

---

## Development

```bash
git clone https://github.com/flowmanner/flowmanner-cli
cd flowmanner-cli
npm install
npm run build           # tsc + copy templates
npm run dev -- --help   # run from src/ via tsx (no build needed)
npm test                # node:test smoke tests
npm run lint
```

To run the CLI against a local backend:

```bash
flowmanner config set baseUrl http://localhost:8000
flowmanner login
```

The default base URL is `https://flowmanner.com`.

---

## Adding a new command

1. Create `src/commands/<name>.ts`. Export a single function:
   ```ts
   export function registerFooCommand(program: Command): void {
     program
       .command("foo")
       .description("...")
       .action(async (opts) => {
         const result = await apiRequest<FooResponse>("/api/v2/foo/");
         // ...
       });
   }
   ```
2. Import and call it from `src/index.ts` after the existing
   `register<...>Command(program)` lines.
3. Add a matching test in `tests/`.
4. Document in this README under **Commands**.

If the command needs a new persistent setting, add it to
`src/lib/config.ts` (schema + getter + setter).

---

## Adding a new template

1. Drop a new YAML file at `src/lib/templates/<name>.yaml`.
2. `npm run build` will copy it to `templates/<name>.yaml`.
3. Users run `flowmanner init <project> --template <name>`.

Templates should be self-contained — assume no prior knowledge of
the user's environment, and document required `inputs` at the top
of the file.

---

## Testing

The repo uses Node's built-in test runner (`node:test`) so we don't
need a separate test framework. Smoke tests live in `tests/`:

- `tests/api.test.ts` — envelope unwrap, error mapping, base URL
- `tests/blueprint.test.ts` — YAML parsing, schema validation
- `tests/config.test.ts` — credentials round-trip, base URL override
- `tests/init.test.ts` — scaffold produces the expected files

End-to-end verification against a real backend is a separate
process — see `docs/cli-e2e.md` (TBD) for the manual checklist.

---

## Roadmap

| Version | Status | Theme |
|---------|--------|-------|
| **v0.1** | current | Login + init + push + publish + run + live progress |
| v0.2 | planned | Additional `init` templates (`pipeline`, `swarm`, `rag`) |
| v0.3 | planned | `flowmanner dev` — local runner that talks to the same LLM endpoints without burning quota |
| v0.4 | planned | Device-flow auth (GitHub-style: paste URL, browser opens, CLI polls) |
| v0.5 | planned | `flowmanner plugin` commands (validate / pack / publish), ported from the internal Python SDK CLI |

The thin-client model is intentional. Anything that needs to
**execute** work runs server-side against the FastAPI + substrate.
Adding a local runner in v0.3 is opt-in (`flowmanner dev`) so the
default install stays small and the substrate stays the source of
truth.

---

## Releasing

1. Bump `version` in `package.json`.
2. `npm run build` — confirms clean compile.
3. `npm test` — confirms smoke tests pass.
4. Tag the commit.
5. `npm publish --access public` from a clean tree.
6. Verify `npx @flowmanner/cli --version` from a fresh shell.

When the package moves to its own repo, this checklist moves with
it; the homelab just pulls `npm install -g @flowmanner/cli` and the
docs page promise (`npm install -g @flowmanner/cli`) becomes true
for everyone.

---

## License

MIT © FlowManner