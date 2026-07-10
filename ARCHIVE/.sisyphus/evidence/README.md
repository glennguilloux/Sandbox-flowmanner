# FlowManner Evidence Capture Rules

Use this directory for agent-executed QA evidence tied to `.sisyphus/plans/*.md` tasks.

## File naming

Use `task-{N}-{scenario-slug}.txt`, for example:

- `task-1-docs-validation-pass.txt`
- `task-1-docs-validation-negative.txt`
- `task-1-substrate-critical-gate.txt`

Replace `{N}` with the plan task number. Keep scenario slugs short and lowercase.

## Required content

Each evidence file must include:

1. The exact command run.
2. The working directory.
3. The exit code.
4. stdout and stderr.
5. A timestamp.

## Safety

Do not include secrets, tokens, session cookies, private keys, or raw credential files. Redact before saving.

## Negative tests

When a command is expected to fail, save the failing output too and name it with a `negative` or `expected-failure` slug. This proves the validation harness catches broken contracts, not only passing ones.
