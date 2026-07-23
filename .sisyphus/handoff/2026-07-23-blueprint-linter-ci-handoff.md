# Exit Audit & Handoff — Blueprint Linter, CI Wiring, and Multi-Repo Audit

**Date:** 2026-07-23
**Author:** Buffy (Freebuff/Kimi coding agent)
**Scope:** Created the multi-repo audit blueprint, built a Python substrate linter for blueprint YAML, wired it into pre-commit/CI, and extended it with per-node required-config validation.

---

## 1. What changed

### Source code / config changes

- `backend/flowmanner-multi-repo-audit.yaml` (new)
  - Pattern B DAG blueprint using the now-fixed `split → merge` substrate path.
  - Splits `inputs.repos`, runs one `sandbox` per repo to audit it, merges results, ranks via `llm_call`, and logs completion.
  - Includes `dependencies: [audit_repo]` on the merge node so both the real substrate and the test fake resolve the join correctly.

- `backend/tests/integration/test_blueprint_integration.py` (modified)
  - Added a fake `_handle_merge` implementation to the integration-test `FakeNodeExecutor`.
  - Added `merge_calls` tracking and fixture cleanup.
  - Added `test_multi_repo_audit_blueprint_splits_merges_and_ranks` to verify per-item fan-out and merge aggregation across the three default repos.

- `backend/scripts/lint_blueprints.py` (new)
  - Discovers `*.yaml` / `*.yml` files under `backend/` and `blueprints/`, skipping excluded dirs.
  - Validates top-level keys (`version`, `name`, `blueprint_type`, `definition`).
  - Validates per-node required config keys, including alternative-key groups (e.g. `variable_set` requires `varName` and either `varValue` or `varExpr`).
  - Runs `validate_blueprint_definition` and `blueprint_to_workflow` from the substrate.
  - Returns non-zero exit code on any failure.

- `backend/tests/test_lint_blueprints.py` (new)
  - Unit tests covering discovery, exclusion, blueprint identification, node constraints, graph validation, adapter conversion, and CLI exit codes.

- `Makefile` (modified)
  - Added `lint-blueprints` target that runs `python scripts/lint_blueprints.py`.

- `.pre-commit-config.yaml` (modified)
  - Added a local `lint-blueprints` hook that runs `make lint-blueprints` when blueprint YAML files are changed.

- `.github/workflows/ci.yml` (modified)
  - Added `lint-blueprints` job that installs Python deps and runs `make lint-blueprints`.

- `backend/.github/workflows/backend-tests.yml` (modified)
  - Added `Lint blueprints` step after the ruff lint step.

- `.github/workflows/pr-check.yml` (modified)
  - Added `Lint blueprints` step after the pytest sanity check, sourcing the existing `/tmp/prcheck-venv`.

- `backend/scripts/lint_blueprints.py` (subsequent extension)
  - Added `NodeConfigSpec` type alias.
  - Added `REQUIRED_NODE_CONFIG` entries for `split`, `merge`, `sandbox`, `llm_call`, and `variable_set`.
  - Improved error messages for missing keys and alternative-key groups.

---

## 2. Status (raw command output)

### git status

```text
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
	modified:   .github/workflows/ci.yml
	modified:   .github/workflows/pr-check.yml
	modified:   Makefile
	modified:   backend/.github/workflows/backend-tests.yml
	modified:   backend/.pre-commit-config.yaml
	modified:   backend/tests/integration/test_blueprint_integration.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	.sisyphus/handoff/2026-07-23-split-merge-aggregation-deploy-handoff.md
	.sisyphus/handoff/TODO-01.md
	backend/flowmanner-multi-repo-audit.yaml
	backend/scripts/lint_blueprints.py
	backend/tests/test_lint_blueprints.py
```

### pytest — blueprint linter unit tests

```text
tests/test_lint_blueprints.py::TestDiscoverYamlFiles::test_finds_yaml_and_yml_files PASSED
tests/test_lint_blueprints.py::TestDiscoverYamlFiles::test_accepts_individual_files PASSED
tests/test_lint_blueprints.py::TestDiscoverYamlFiles::test_ignores_missing_paths PASSED
tests/test_lint_blueprints.py::TestDiscoverYamlFiles::test_skips_excluded_directories PASSED
tests/test_lint_blueprints.py::TestDiscoverYamlFiles::test_exclusion_is_exact_match PASSED
tests/test_lint_blueprints.py::TestIsExcluded::test_excluded_dirs_are_skipped PASSED
tests/test_lint_blueprints.py::TestIsExcluded::test_non_excluded_dirs_are_allowed PASSED
tests/test_lint_blueprints.py::TestLooksLikeBlueprint::test_true_when_keys_present PASSED
tests/test_lint_blueprints.py::TestLooksLikeBlueprint::test_false_when_key_missing PASSED
tests/test_lint_blueprints.py::TestLooksLikeBlueprint::test_false_when_not_dict PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_split_node_requires_splitOn PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_merge_node_requires_mergeStrategy PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_sandbox_node_requires_task_prompt PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_valid_nodes_pass PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_unknown_node_types_are_ignored PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_non_list_nodes_is_noop PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_missing_config_treated_as_empty PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_llm_call_requires_prompt PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_llm_call_with_prompt_passes PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_variable_set_requires_varName PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_variable_set_requires_varValue_or_varExpr PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_variable_set_with_varValue_passes PASSED
tests/test_lint_blueprints.py::TestValidateNodeConstraints::test_variable_set_with_varExpr_passes PASSED
tests/test_lint_blueprints.py::TestValidateBlueprint::test_valid_blueprint_passes PASSED
tests/test_lint_blueprints.py::TestValidateBlueprint::test_missing_required_keys_reported PASSED
tests/test_lint_blueprints.py::TestValidateBlueprint::test_definition_must_be_mapping PASSED
tests/test_lint_blueprints.py::TestValidateBlueprint::test_graph_validator_errors_returned PASSED
tests/test_lint_blueprints.py::TestValidateBlueprint::test_adapter_invalid_graph_error PASSED
tests/test_lint_blueprints.py::TestValidateBlueprint::test_unexpected_adapter_error_reported PASSED
tests/test_lint_blueprints.py::TestMain::test_returns_zero_when_all_blueprints_valid PASSED
tests/test_lint_blueprints.py::TestMain::test_returns_one_when_blueprint_invalid PASSED
tests/test_lint_blueprints.py::TestMain::test_returns_one_on_yaml_parse_error PASSED
tests/test_lint_blueprints.py::TestMain::test_non_blueprint_yaml_is_ignored PASSED
tests/test_lint_blueprints.py::TestMain::test_excluded_dirs_are_skipped_in_main PASSED

35 passed in 0.08s
```

### pytest — blueprint integration tests

```text
tests/integration/test_blueprint_integration.py::test_multi_repo_audit_blueprint_splits_merges_and_ranks PASSED
```

### make lint-blueprints

```text
Scanning 13 YAML file(s) for blueprints...

✅ backend/flowmanner-ab-arena.yaml
✅ backend/flowmanner-cache-warmer.yaml
✅ backend/flowmanner-institutional-memory.yaml
✅ backend/flowmanner-multi-repo-audit.yaml
✅ backend/flowmanner-rag-report.yaml
✅ blueprints/auth-flow-tester.yaml
 blueprints/scrape-diff-alert.yaml
✅ blueprints/web-recon.yaml

All 8 blueprint(s) passed validation.
```

---

## 3. What did not change but was inspected

- `backend/app/services/substrate/node_executor.py` — inspected to confirm required config keys for `split`, `merge`, `sandbox`, `llm_call`, and `variable_set`.
- `backend/app/services/substrate/adapters.py` — `validate_blueprint_definition` and `blueprint_to_workflow` are reused by the linter.
- `backend/flowmanner-cache-warmer.yaml` — inspected; the existing split-only path still passes linting.
- `.github/workflows/deploy.yml` and other deployment workflows — not modified.

---

## 4. Next session handoff

What the next agent should know:

1. **The blueprint linter is now a first-class gate.**
   - `make lint-blueprints` validates all project blueprints.
   - It runs in pre-commit, root CI, backend CI, and the self-hosted PR check.
   - It enforces per-node required config keys; extend `REQUIRED_NODE_CONFIG` in `backend/scripts/lint_blueprints.py` as new node types gain required keys.

2. **The multi-repo audit blueprint is ready for use but not deployed.**
   - File: `backend/flowmanner-multi-repo-audit.yaml`
   - It relies on the split → merge aggregation fix from the prior handoff.
   - Do NOT deploy or run `flowmanner push` without human review.

3. **Tests to keep green.**
   - `backend/tests/test_lint_blueprints.py` (35 tests).
   - `backend/tests/integration/test_blueprint_integration.py::test_multi_repo_audit_blueprint_splits_merges_and_ranks`.

4. **Open optional polish.**
   - Move the `__split_aggregate__` marker constant to `workflow_models.py` to remove literal-string duplication between `dag.py` and `node_executor.py`.
   - Add stricter value validation (e.g. `varName` non-empty/whitespace-only) in the linter.
   - Extend `REQUIRED_NODE_CONFIG` with additional node types as the substrate evolves.
   - Run a live end-to-end `flowmanner run` against the multi-repo audit blueprint with real repos.

---

## 5. Deliverable summary for the human

- ✅ Multi-repo audit blueprint created and validated.
- ✅ Blueprint linter created with discovery, exclusion, and validation paths.
- ✅ Node-specific constraint validation added for `split`, `merge`, `sandbox`, `llm_call`, and `variable_set`.
- ✅ Linter wired into pre-commit hooks and three CI workflows.
- ✅ Unit tests and integration tests added and passing.
- ⛔ Not pushed or deployed — awaiting review.

**Decision for the human:** review the new blueprint, the linter implementation, and the CI/pre-commit wiring; then either approve for merge or request scope changes.
