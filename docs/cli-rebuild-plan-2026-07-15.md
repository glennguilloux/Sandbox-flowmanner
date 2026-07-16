# Flowmanner CLI — Rebuild Plan (synthesized & independently verified)

**Author:** Orchestrator (Hermes Lead Backend Architect persona) over two persona-injected
Kanban workers: a `backend-architect` (fmw1) design card + a `code-reviewer` (fmw2) audit card.
Both ran READ-ONLY in isolated git worktrees and blocked for review. This doc corrects a
material error in the architect's draft (see §0) and consolidates the verified findings.

Repo root: `/opt/flowmanner`. Backend at `/opt/flowmanner/backend/`. SDK at `/opt/flowmanner/sdk-python/`.

> **Naming (do not confuse — these are two different words):**
> - **Flowmanner** (one P) = the product / company / brand, and `https://flowmanner.com`.
> - **flowmanner** (double P) = the ACTUAL spelling of the SDK package + command in THIS repo:
>   distribution `flowmanner-api-client`, import `flowmanner_api_client`, console script `flowmanner`.
>   The doc uses `flowmanner` for code/command names and `flowmanner` for the brand. Both are correct
>   as written; do NOT "unify" them. (The local throwaway test DB in
>   `backend/tests/test_substrate_idempotency_unique.py` is also named `flowmanner` — unrelated to the
>   brand, harmless, not touched.)

---

## 0. ⚠️ Corrected ground-truth (verified against LIVE infra, not just source)

The architect's draft asserted the live route is `/api/missions` and that the built/raw-httpx
copy fails on **every** mission call with a 404. I verified against the real deployed API:

```
curl https://flowmanner.com/api/missions          → HTTP 401   (route EXISTS)
curl https://flowmanner.com/api/v1/missions       → HTTP 404   (route does NOT exist)
curl https://flowmanner.com/api/v1/usage/summary  → HTTP 401   (route EXISTS)
curl https://flowmanner.com/api/health            → HTTP 200
```

Conclusion (the author's corrected reading):
- The source tree's `/api/missions` paths are **CORRECT** (401 = routed, auth-gated).
- The built copy's `/api/v1/missions` paths are **WRONG** (404 = no such route). The
  architect was right that the built copy 404s — but WRONG that this makes the source copy
  flawless. The source copy's `missions list` **still crashes** on the envelope (reviewer's
  finding #3). So neither copy is fully correct; both need work.
- `/api/v1/usage/summary` and `/api/health` resolve — so `costs` and `status` are fine in both.

> The architect's premise "the built copy is broken on every mission call (404)" is TRUE, but
> its corollary "the source tree is correct everywhere" is FALSE. The plan below treats both
> bugs as real.

---

## 1. The three problems (consolidated, all verified)

### 🔴 P1 — Dead PATH shim
`/home/glenn/.local/bin/flowmanner` is:
```sh
#!/bin/sh
exec hermes -p flowmanner "$@"
```
`-p flowmanner` selects a Hermes **profile** that does not exist (profiles: default, fmw1, fmw2,
fmw3, fmw_synth). Every `flowmanner …` invocation fails with `Profile 'flowmanner' does not exist.`
*100% of calls die at the shell layer.* The shim is also conceptually wrong — `hermes -p` picks an
agent profile, it does not launch a console script.

### 🔴 P2 — Two divergent SDK packages, install collision
- `sdk-python/flowmanner_api_client/` — **SOURCE** tree (generated client). `cli.py` wraps the
  auto-generated low-level client. Subcommands: `status`, `costs`, `missions list|get|create`.
- `sdk-python/flowmanner-api-client/` — **BUILT** copy (raw httpx rewrite). Its `cli.py` is a
  leaner variant (only `status`, `costs`, `missions` — `get`/`create` missing).
- BOTH declare the same distribution name `flowmanner-api-client` and import package
  `flowmanner_api_client`.
- Only the **BUILT** copy's `pyproject.toml` registers a console script:
  `sdk-python/flowmanner-api-client/pyproject.toml:32-33` →
  `[tool.poetry.scripts] flowmanner = "flowmanner_api_client.cli:main"`.
  The **source** `sdk-python/pyproject.toml` has **NO** `[tool.poetry.scripts]` entry, so as it
  stands the source tree produces **no** `flowmanner` command on install.
- `diff` of the two `cli.py`: full-file rewrite (219 → 64 lines); flag/env drift
  (`--api-key`/`FLOWMANNER_BASE_URL` vs `--key`/`FLOWMANNER_URL`); built copy sends `?limit=`
  while the route wants `page`/`per_page`.

### 🔴 P3 — `missions list` envelope mismatch (crashes in BOTH copies)
Backend `backend/app/api/v1/mission.py:52-68` (`list_items`) returns a **dict envelope**:
```python
return {"items": r.items, "total": ..., "page": ..., "per_page": ..., "pages": ...}
```
- **Source copy** (`sdk-python/flowmanner_api_client/cli.py:100-118`): `list(missions)` on the
  dict → iterates **keys** (strings) → `m['id']` → `TypeError: string indices must be integers`.
- **Built copy** (`.../flowmanner-api-client/flowmanner_api_client/cli.py:40-46`): same `for m in
  missions: m['id']` on the envelope dict keys → identical `TypeError`.
- Live proof: `curl /api/missions` returns 401 (so the route is reached); with auth it returns the
  `{items,...}` envelope; **both CLIs then crash** on it.

### 🟡 P4 — Built copy 404s on every mission call (path bug)
Built copy hits `/api/v1/missions*` (verified 404 above). Route is `/api/missions`. This alone
disqualifies the built copy as the survivor.

### 🟡 P5 — `costs` breakdown field-name mismatch (source copy)
Backend `UsageByModel` fields are `model_id` / `prompt_tokens` / `completion_tokens` / `cost`
(`backend/app/api/v1/usage.py:36-42`; model `sdk-python/flowmanner_api_client/models/usage_by_model.py:23-27`).
Source `cmd_costs` (`cli.py:83-90`) reads `item.model` / `item.tokens` → prints `unknown`/`0` for
model + tokens (cost column is right).

### 🟡 P6 — Test gives false confidence
`sdk-python/flowmanner-api-client/tests/test_cli.py` mocks `list_missions.return_value = [...]` (a
bare list) — never the real dict envelope — so it passes while production raises `TypeError`. The
source tree has **no tests at all**.

### 💭 P7 — nits
Private-attr access `fm._client.base_url` (`cli.py:62`); bare `Exception` swallows 401 with a
generic message; built `cli.py:17` `add_argument("list", nargs="?")` is malformed.

---

## 2. Recommended rebuild (single source-of-truth)

**KEEP** `sdk-python/flowmanner_api_client/` (generated source tree — correct paths, type-safe,
regenerable). **DELETE** `sdk-python/flowmanner-api-client/` (built fork — wrong paths, no
generator, duplicates the package name). Then:

1. **Add the missing console-script entry** to `sdk-python/pyproject.toml`:
   ```toml
   [tool.poetry.scripts]
   flowmanner = "flowmanner_api_client.cli:main"
   [tool.poetry.group.dev.dependencies]
   pytest = "^8.0"
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   ```
   (Package name `flowmanner-api-client` and import `flowmanner_api_client` stay as-is; do NOT
   rename the import to `flowmanner`.)

2. **Fix `missions list`** in `sdk-python/flowmanner_api_client/cli.py` `cmd_missions_list`
   (replace the unwrap at 100-118): unwrap `result["items"]` when the response is the dict
   envelope, fall back to a bare list for backward-compat, and print the `total/pages` footer.
   (Exact patch supplied by the architect at §B.2 of its design file.)

3. **Fix `costs` breakdown** field names in `cli.py:83-90` → `model_id` / `prompt_tokens` /
   `completion_tokens` / `cost`.

4. **Port tests** from the built copy into `sdk-python/tests/` AND add a live-contract envelope
   test (`test_missions_list_envelope.py`) that mocks the **real `{items,...}` shape** and asserts
   the CLI iterates `.items` (not keys). This is the regression guard for P3.

5. **Install + replace the shim:**
   ```bash
   cd /opt/flowmanner/sdk-python
   pip install -e .                        # or: poetry install
   which -a flowmanner                     # expect: <venv>/bin/flowmanner
   flowmanner status                       # should hit /api/health, not a missing profile
   # only AFTER the above confirms the real script:
   rm -f /home/glenn/.local/bin/flowmanner
   hash -r; which -a flowmanner
   ```
   Order matters: install first, delete shim last, or `flowmanner` vanishes from PATH.

6. **Delete the built duplicate** `sdk-python/flowmanner-api-client/` (after tests are ported):
   `git rm -r sdk-python/flowmanner-api-client && rm -rf "sdk-python/flowmanner-api-client"`.

> Note: the architect flagged a filesystem oddity — `sdk-python/flowmanner-api-client/` is
> git-tracked and readable via `find`/`read_file` but a plain `ls -ld`/`test -f` reported "No such
> file or directory" in its worktree. Confirm the working-tree contents are intact (not a broken
> symlink / oddly-named dir) before `git rm`.

---

## 3. Verification gate (run before declaring done)

- `cd /opt/flowmanner/sdk-python && pip install -e .[dev] && pytest -q` — envelope test + ported
  tests green.
- `ruff check` on the edited `cli.py` (repo `ruff.toml` selects `G`; `G004` f-string-in-logger is a
  hard fail — but `cli.py` uses `print()`, so only matters if a worker reintroduces logging).
- `flowmanner --help` resolves to the venv script (not the shim).
- `flowmanner missions list` (with a real `FLOWMANNER_API_KEY`) iterates `.items` and prints the
  `total` footer — no `TypeError`.
- `flowmanner status` → hits `/api/health` (live: 200). `flowmanner costs` → `/api/v1/usage/summary`.

---

## 4. Open decisions (D1 decided by Glenn; D2/D3 pending his call)

- **D1 — KEEP THE THREE CLIs SEPARATE. (DECIDED by Glenn, 2026-07-15.)**
  Decision: `flowmanner` SDK CLI, `runtime-cli`, and plugin `sdk/cli.py` remain THREE independent
  entry points. Do NOT combine them into one binary. No code merge, no shared launcher.
  - `flowmanner`  → `sdk-python/flowmanner_api_client/cli.py`  (end-user API: status/costs/missions)
  - `runtime-cli` → `backend/app/cli/runtime_cli.py`            (infra-ops: /api/runtime/*)
  - plugin tool  → `backend/app/sdk/cli.py` (`python -m app.sdk.cli`)  (local plugin validate/pack/unpack)
  Reason: distinct audiences and dependency footprints; unrelated API surfaces. Folding them adds
  confusion with no benefit. If a single launcher is ever wanted later, it would be thin subcommand
  *wrappers* only — and only after Glenn asks.
- **D2 — Generated wrapper vs raw-httpx?** Plan keeps the generated wrapper (correct paths,
  regenerable, type-safe). The raw-httpx copy is disqualified by the 404 (P4).
- **D3 — Pagination exposure?** Source `cli.py` exposes only `--limit` (→ `per_page`, page 1 only).
  Add `--page`/`--per_page` to match the contract? Architect recommends (b) — expose both, keep
  `--limit` as an alias for `--per_page`.

---

## 5. Highest-risk ordering

1. Fix `missions list` envelope unwrap (P3) — tiny, localized, unblocks the headline command.
2. Add `[tool.poetry.scripts]` to source `pyproject.toml` (P2 root cause of the PATH gap).
3. Port + add envelope test (P6 — locks the fix).
4. Install editable; confirm `which flowmanner` → venv script.
5. Delete dead shim (P1) — only after step 4.
6. Delete built duplicate (P2/P4) — after tests ported.
7. `costs` field-name fix (P5) + D1/D2/D3 cleanups.

---

## 6. Source deliverables (worker artifacts)

- Audit (facts-only): `.worktrees/t_e2b85fef/.hermes/audit/CLI-CURRENT-STATE-AUDIT.md`
- Design: `.worktrees/t_cf026a31/.hermes/audit/CLI-REBUILD-DESIGN.md`
- Both git-clean (no source commits); verified here against live `flowmanner.com` endpoints.
- Kanban cards: `t_cf026a31` (architect, blocked), `t_e2b85fef` (reviewer, blocked).
