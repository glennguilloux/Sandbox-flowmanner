"""
Git Repo Manager — Agent-callable tool for Git repository operations.

git_repo_manager → clone, branch, commit, push, and PR creation via subprocess + GitHub API.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", os.getenv("GITHUB_ACCESS_TOKEN", ""))
GITHUB_API_BASE = "https://api.github.com"
GIT_BIN = shutil.which("git") or "/usr/bin/git"
DEFAULT_TIMEOUT = int(os.getenv("GIT_HTTP_TIMEOUT", "60"))
WORK_DIR_BASE = os.getenv("GIT_WORK_DIR", "/tmp/git_repo_manager")


GIT_ACTIONS: tuple[str, ...] = (
    "clone",
    "checkout_branch",
    "create_branch",
    "commit",
    "push",
    "pull",
    "create_pr",
    "get_status",
    "list_branches",
    "get_diff",
    "get_log",
    "cleanup",
)


# ── Input ───────────────────────────────────────────────────────────


class GitRepoManagerInput(ToolInput):
    action: str = Field(
        ...,
        description=(
            "Git operation: 'clone', 'checkout_branch', 'create_branch', 'commit', "
            "'push', 'pull', 'create_pr', 'get_status', 'list_branches', 'get_diff', 'get_log'"
        ),
    )
    repo_url: str | None = Field(
        None,
        description="Repository URL (https://github.com/owner/repo.git). Required for clone.",
    )
    branch: str | None = Field(
        None,
        description="Branch name for checkout, create_branch, or push.",
    )
    message: str | None = Field(
        None,
        description="Commit message for commit action.",
    )
    files: list[str] | None = Field(
        None,
        description="List of file paths to stage for commit. If empty, commits all changes.",
    )
    pr_title: str | None = Field(
        None,
        description="PR title for create_pr action. Auto-pushes current branch before creating PR.",
    )
    pr_body: str | None = Field(
        None,
        description="PR body/description for create_pr action.",
    )
    pr_base: str | None = Field(
        "main",
        description="Base branch for PR (default: main).",
    )
    work_dir: str | None = Field(
        None,
        description="Working directory path for an existing repo. Overrides auto-detection.",
    )
    max_log_entries: int | None = Field(
        20,
        description="Maximum number of log entries to return for get_log.",
    )


# ── Tool ────────────────────────────────────────────────────────────


class GitRepoManagerTool(BaseTool):
    """Clone, branch, commit, push, and create PRs via git CLI + GitHub API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="git_repo_manager",
            name="Git Repo Manager",
            description=(
                "Clone, branch, commit, push, and create pull requests in Git repositories. "
                "Uses the local git CLI for file operations and the GitHub REST API for PR creation. "
                "Requires GITHUB_TOKEN env var for PR operations."
            ),
            category="developer-tools",
            input_schema=GitRepoManagerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "result": {"type": "object"},
                },
            },
            tags=["git", "github", "devops", "developer"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GitRepoManagerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(self.tool_id, f"Invalid input: {e}")

        if validated.action not in GIT_ACTIONS:
            return ToolResult.error_result(
                self.tool_id,
                f"Unknown action '{validated.action}'. Use one of: {', '.join(GIT_ACTIONS)}",
            )

        result = await self._execute_action(validated)
        return ToolResult.success_result(self.tool_id, result)

    async def _execute_action(self, v: GitRepoManagerInput) -> dict[str, Any]:
        action = v.action

        if action == "clone":
            return await self._clone(v)
        elif action == "checkout_branch":
            return await self._checkout(v)
        elif action == "create_branch":
            return await self._create_branch(v)
        elif action == "commit":
            return await self._commit(v)
        elif action == "push":
            return await self._push(v)
        elif action == "pull":
            return await self._pull(v)
        elif action == "create_pr":
            return await self._create_pr(v)
        elif action == "get_status":
            return await self._status(v)
        elif action == "list_branches":
            return await self._list_branches(v)
        elif action == "get_diff":
            return await self._diff(v)
        elif action == "get_log":
            return await self._log(v)
        elif action == "cleanup":
            return await self._cleanup(v)
        return {"error": f"Action '{action}' not implemented"}

    # ── helpers ────────────────────────────────────────────────────

    async def _run_git(
        self, args: list[str], cwd: str | None = None, timeout: int = DEFAULT_TIMEOUT
    ) -> tuple[int, str, str]:
        """Run a git command and return (returncode, stdout, stderr)."""
        cmd = [GIT_BIN, *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, "", f"Git command timed out after {timeout}s: {' '.join(cmd)}"

        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
        )

    def _resolve_work_dir(self, v: GitRepoManagerInput) -> str | None:
        """Resolve the best working directory from input or env."""
        if v.work_dir and os.path.isdir(v.work_dir):
            return v.work_dir

        # Try to extract repo name from repo_url
        if v.repo_url:
            repo_name = self._parse_repo_name(v.repo_url)
            candidate = os.path.join(WORK_DIR_BASE, repo_name)
            if os.path.isdir(candidate):
                return candidate

        return None

    @staticmethod
    def _parse_repo_name(repo_url: str) -> str:
        """Extract the repository name from any GitHub URL format.

        Handles:
        - https://github.com/owner/repo.git
        - git@github.com:owner/repo.git
        - ssh://git@github.com/owner/repo.git
        """
        # Strip trailing slashes and .git suffix
        clean = repo_url.rstrip("/")
        if clean.endswith(".git"):
            clean = clean[:-4]

        # SSH format: git@github.com:owner/repo
        if "@" in clean and ":" in clean:
            # git@github.com:owner/repo
            parts = clean.split(":")
            if len(parts) >= 2:
                path_parts = parts[-1].split("/")
                if path_parts:
                    return path_parts[-1]

        # HTTPS or ssh:// format: ...github.com/owner/repo
        parts = clean.split("/")
        if parts:
            return parts[-1]

        return clean

    @staticmethod
    def _parse_github_repo(repo_url: str) -> tuple[str, str]:
        """Parse owner and repo name from any GitHub URL format.

        Handles:
        - https://github.com/owner/repo.git      → (owner, repo)
        - git@github.com:owner/repo.git           → (owner, repo)
        - ssh://git@github.com/owner/repo.git     → (owner, repo)
        """
        clean = repo_url.rstrip("/")
        if clean.endswith(".git"):
            clean = clean[:-4]

        # SSH format: git@github.com:owner/repo → split on colon
        if "@" in clean and ":" in clean:
            # git@github.com:owner/repo or ssh://git@github.com/owner/repo
            if clean.startswith("ssh://"):
                clean = clean[len("ssh://") :]
                # Now: git@github.com/owner/repo
                if "@" in clean:
                    clean = clean.split("@", 1)[1]
                parts = clean.split("/")
            else:
                # git@github.com:owner/repo
                host_and_path = clean.split(":", 1)
                parts = host_and_path[1].split("/") if len(host_and_path) >= 2 else []
        else:
            # HTTPS: https://github.com/owner/repo
            parts = clean.split("/")

        if len(parts) >= 2:
            return parts[-2], parts[-1]
        return "", ""

    # ── actions ────────────────────────────────────────────────────

    async def _clone(self, v: GitRepoManagerInput) -> dict[str, Any]:
        if not v.repo_url:
            return {"action": "clone", "error": "repo_url is required for clone"}

        os.makedirs(WORK_DIR_BASE, exist_ok=True)
        repo_name = self._parse_repo_name(v.repo_url)
        target_dir = os.path.join(WORK_DIR_BASE, repo_name)

        args = ["clone"]
        if v.branch:
            args.extend(["-b", v.branch])
        args.extend([v.repo_url, target_dir])

        rc, stdout, stderr = await self._run_git(args, timeout=300)
        if rc != 0:
            return {
                "action": "clone",
                "repo_url": v.repo_url,
                "error": stderr or stdout,
            }

        return {
            "action": "clone",
            "repo_url": v.repo_url,
            "target_dir": target_dir,
            "branch": v.branch,
            "output": stdout or "Repository cloned successfully",
        }

    async def _checkout(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {
                "action": "checkout_branch",
                "error": "No work_dir available; clone a repo first or set work_dir",
            }

        branch = v.branch or "main"
        rc, stdout, stderr = await self._run_git(["checkout", branch], cwd=cwd)
        if rc != 0:
            # Try fetching first, then checkout
            await self._run_git(["fetch", "origin"], cwd=cwd)
            rc, stdout, stderr = await self._run_git(["checkout", branch], cwd=cwd)

        return {
            "action": "checkout_branch",
            "branch": branch,
            "work_dir": cwd,
            "output": stdout or f"Checked out {branch}",
            "error": stderr if rc != 0 else None,
        }

    async def _create_branch(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {"action": "create_branch", "error": "No work_dir available"}

        if not v.branch:
            return {"action": "create_branch", "error": "branch name is required"}

        rc, stdout, stderr = await self._run_git(["checkout", "-b", v.branch], cwd=cwd)
        return {
            "action": "create_branch",
            "branch": v.branch,
            "work_dir": cwd,
            "output": stdout or f"Created and checked out branch '{v.branch}'",
            "error": stderr if rc != 0 else None,
        }

    async def _commit(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {"action": "commit", "error": "No work_dir available"}

        if not v.message:
            return {"action": "commit", "error": "message is required for commit"}

        # Stage files
        if v.files:
            for f in v.files:
                rc, _, stderr = await self._run_git(["add", f], cwd=cwd)
                if rc != 0:
                    return {
                        "action": "commit",
                        "error": f"Failed to stage {f}: {stderr}",
                    }
        else:
            await self._run_git(["add", "-A"], cwd=cwd)

        # Set git user if not configured
        await self._ensure_git_config(cwd)

        rc, stdout, stderr = await self._run_git(["commit", "-m", v.message], cwd=cwd)
        if rc != 0 and "nothing to commit" in (stdout + stderr).lower():
            return {
                "action": "commit",
                "output": "Nothing to commit (working tree clean)",
            }

        return {
            "action": "commit",
            "message": v.message,
            "work_dir": cwd,
            "output": stdout or stderr or "Changes committed",
            "error": stderr if rc != 0 else None,
        }

    async def _push(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {"action": "push", "error": "No work_dir available"}

        args = ["push"]
        if v.branch:
            args.extend(["origin", v.branch])
        else:
            # Push current branch to origin
            rc, stdout, _ = await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
            if rc == 0 and stdout:
                args.extend(["origin", stdout])

        rc, stdout, stderr = await self._run_git(args, cwd=cwd, timeout=120)
        return {
            "action": "push",
            "branch": v.branch,
            "work_dir": cwd,
            "output": stdout or "Push completed",
            "error": stderr if rc != 0 else None,
        }

    async def _pull(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {"action": "pull", "error": "No work_dir available"}

        args = ["pull", "origin"]
        if v.branch:
            args.append(v.branch)

        rc, stdout, stderr = await self._run_git(args, cwd=cwd, timeout=120)
        return {
            "action": "pull",
            "branch": v.branch,
            "work_dir": cwd,
            "output": stdout or "Pull completed",
            "error": stderr if rc != 0 else None,
        }

    async def _create_pr(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {"action": "create_pr", "error": "No work_dir available"}

        if not GITHUB_TOKEN:
            return {
                "action": "create_pr",
                "error": "GITHUB_TOKEN env var not set — cannot create PR via API",
            }

        # Determine head branch
        rc, head_branch, _ = await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
        if rc != 0 or not head_branch:
            return {
                "action": "create_pr",
                "error": "Could not determine current branch",
            }

        # Push first if needed
        await self._run_git(["push", "origin", head_branch], cwd=cwd, timeout=120)

        # Get remote origin URL to parse owner/repo
        rc, remote_url, _ = await self._run_git(["config", "--get", "remote.origin.url"], cwd=cwd)
        if rc != 0 or not remote_url:
            return {
                "action": "create_pr",
                "error": "Could not determine remote origin URL",
            }

        owner, repo = self._parse_github_repo(remote_url)
        if not owner or not repo:
            return {
                "action": "create_pr",
                "error": f"Could not parse owner/repo from: {remote_url}",
            }

        base = v.pr_base or "main"
        title = v.pr_title or f"PR from {head_branch}"
        body = v.pr_body or ""

        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload: dict[str, Any] = {
            "title": title,
            "head": head_branch,
            "base": base,
        }
        if body:
            payload["body"] = body

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
                json=payload,
                headers=headers,
            )
            if resp.status_code >= 400:
                return {
                    "action": "create_pr",
                    "error": f"GitHub API error {resp.status_code}: {resp.text[:500]}",
                }
            pr_data = resp.json()
            return {
                "action": "create_pr",
                "pr_url": pr_data.get("html_url"),
                "pr_number": pr_data.get("number"),
                "title": pr_data.get("title"),
                "state": pr_data.get("state"),
                "head": head_branch,
                "base": base,
            }

    async def _status(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {"action": "get_status", "error": "No work_dir available"}

        _rc, stdout, _stderr = await self._run_git(["status", "--porcelain"], cwd=cwd)
        lines = [l for l in stdout.split("\n") if l.strip()] if stdout else []
        _rc2, branch, _ = await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)

        return {
            "action": "get_status",
            "work_dir": cwd,
            "branch": branch or "unknown",
            "changed_files": lines,
            "changed_count": len(lines),
            "is_clean": len(lines) == 0,
        }

    async def _list_branches(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {"action": "list_branches", "error": "No work_dir available"}

        # Local branches
        _rc1, local, _ = await self._run_git(["branch"], cwd=cwd)
        local_branches = [b.lstrip("* ").strip() for b in local.split("\n") if b.strip()] if local else []

        # Current branch
        _rc2, current, _ = await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)

        return {
            "action": "list_branches",
            "work_dir": cwd,
            "current_branch": current or "unknown",
            "branches": local_branches,
            "branch_count": len(local_branches),
        }

    async def _diff(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {"action": "get_diff", "error": "No work_dir available"}

        _rc, stdout, _stderr = await self._run_git(["diff"], cwd=cwd)
        lines = stdout.split("\n") if stdout else []

        return {
            "action": "get_diff",
            "work_dir": cwd,
            "diff": stdout[:20000] if stdout else "",  # truncate large diffs
            "line_count": len(lines),
            "has_changes": len(stdout) > 0 if stdout else False,
        }

    async def _log(self, v: GitRepoManagerInput) -> dict[str, Any]:
        cwd = self._resolve_work_dir(v)
        if not cwd:
            return {"action": "get_log", "error": "No work_dir available"}

        max_entries = v.max_log_entries or 20
        _rc, stdout, _ = await self._run_git(["log", f"-{max_entries}", "--oneline", "--decorate"], cwd=cwd)
        entries = [e.strip() for e in stdout.split("\n") if e.strip()] if stdout else []

        return {
            "action": "get_log",
            "work_dir": cwd,
            "entries": entries,
            "entry_count": len(entries),
        }

    async def _ensure_git_config(self, cwd: str) -> None:
        """Set default git user name/email if not already configured globally or locally."""
        for key, default in [
            ("user.name", "Flowmanner Agent"),
            ("user.email", "agent@flowmanner.local"),
        ]:
            # Check global config first
            rc_g, val_g, _ = await self._run_git(["config", "--global", key], cwd=cwd)
            if rc_g == 0 and val_g:
                continue
            # Then check local config
            rc_l, val_l, _ = await self._run_git(["config", key], cwd=cwd)
            if rc_l == 0 and val_l:
                continue
            # Set local only if neither is configured
            await self._run_git(["config", key, default], cwd=cwd)

    async def _cleanup(self, v: GitRepoManagerInput) -> dict[str, Any]:
        """Remove cloned working directories to free disk space."""
        import shutil

        if v.work_dir and os.path.isdir(v.work_dir):
            try:
                shutil.rmtree(v.work_dir)
                return {"action": "cleanup", "removed": v.work_dir}
            except Exception as e:
                return {
                    "action": "cleanup",
                    "error": f"Failed to remove {v.work_dir}: {e}",
                }

        # Clean up all repos under WORK_DIR_BASE
        if os.path.isdir(WORK_DIR_BASE):
            removed = []
            for entry in os.listdir(WORK_DIR_BASE):
                full_path = os.path.join(WORK_DIR_BASE, entry)
                if os.path.isdir(full_path):
                    try:
                        shutil.rmtree(full_path)
                        removed.append(full_path)
                    except Exception:
                        logger.debug("git_cleanup_rmtree_failed", exc_info=True)
            return {"action": "cleanup", "removed_dirs": removed, "count": len(removed)}

        return {"action": "cleanup", "removed_dirs": [], "count": 0}


# ── Register ────────────────────────────────────────────────────────

register_tool(GitRepoManagerTool())
