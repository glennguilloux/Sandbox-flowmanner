# GitHub Actions Workflows

[![CI](https://github.com/glennguilloux/Sandbox-flowmanner/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/glennguilloux/Sandbox-flowmanner/actions/workflows/ci.yml)

This document describes the CI/CD workflows in the Flowmanner project. The workflow definitions live in `.github/workflows/`.

## Table of Contents

- [CI (`ci.yml`)](#ci-ciyml)
  - [`lint-blueprints`](#lint-blueprints)
  - [`docs-and-node-type-table-drift`](#docs-and-node-type-table-drift)
  - [`backend`](#backend)
  - [Why the path filters skip steps instead of jobs](#why-the-path-filters-skip-steps-instead-of-jobs)
- [Other Workflows](#other-workflows)

## CI (`ci.yml`)

Runs on every `push` to `main` and every `pull_request` targeting `main`.

### Jobs

#### `lint-blueprints`

Validates all blueprint YAML files using `backend/scripts/lint_blueprints.py`.

Because this job is a hard dependency of the `backend` job (`needs: [substrate-critical, lint-blueprints]`), the job itself always runs. However, the actual work steps are skipped unless one of the following changed:

- `backend/flowmanner-*.yaml`
- `blueprints/**/*.yaml`
- `backend/scripts/lint_blueprints.py`

This means that on a PR that only touches, for example, a frontend file or a README, the `lint-blueprints` job will still show a green check mark, but the linting step will be skipped. This is intentional: it keeps the required status check green while avoiding unnecessary work.

#### `docs-and-node-type-table-drift`

Runs the drift tests that guard generated docs and repository references:

- `backend/tests/test_lint_blueprints.py::TestNodeTypeTableDrift` — regenerates the substrate node type table and asserts it matches the committed `backend/docs/substrate-node-types-table.md`.
- `backend/tests/test_docs_drift.py` — documentation-only drift tests:
  - `TestDocsWorkflowsBadgeUrl` — asserts the CI badge URL in `docs/workflows.md` matches the git remote.
  - `TestDocsRepoUrlDrift` — asserts GitHub URLs in project markdown files match the canonical repo.

Like `lint-blueprints`, the job always runs but skips the actual test unless one of the following changed:

- `backend/scripts/lint_blueprints.py`
- `backend/scripts/generate_node_type_table.py`
- `backend/app/services/substrate/node_executor.py`
- `backend/app/services/substrate/workflow_models.py`
- `backend/docs/substrate-node-types-table.md`

#### `backend`

Runs Ruff, mypy, and the backend pytest suite. It depends on `substrate-critical` and `lint-blueprints`, so it will only start after those jobs succeed.

### Why the path filters skip steps instead of jobs

GitHub Actions `needs` can only reference jobs within the same workflow file. If we skipped the entire `lint-blueprints` job based on changed paths, the `backend` job would also be skipped (because one of its dependencies was skipped). By using `dorny/paths-filter` to skip the *steps* inside `lint-blueprints`, the job always succeeds, the `backend` job is unblocked, and the PR still gets a separate green check for `lint-blueprints`.

## Other Workflows

- `pr-check.yml`: Self-hosted sanity checks for pull requests. It also runs `make lint-blueprints` as a final local guard, independent of the `ci.yml` job.
- `deploy.yml`: Production deployment workflow.
- `cli.yml`, `load-test.yml`, `publish-sdk-testpypi.yml`: CLI, load testing, and SDK publishing workflows.
