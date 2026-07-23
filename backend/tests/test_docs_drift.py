"""Tests that documentation files stay in sync with the repository state.

These checks are not specific to ``lint_blueprints.py``; they guard against
stale GitHub URLs, workflow badge drift, and similar documentation rot. They
require a git checkout because they compare committed docs against the current
``origin`` remote.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


def _parse_github_owner_repo(url: str) -> str:
    """Extract 'owner/repo' from HTTPS or SSH git/GitHub URLs.

    Examples:
        https://github.com/owner/repo.git          -> owner/repo
        https://github.com/owner/repo              -> owner/repo
        git@github.com:owner/repo.git              -> owner/repo
        git@github.com:owner/repo                  -> owner/repo
    """
    url = url.strip()
    if url.startswith("https://github.com/"):
        path = url[len("https://github.com/") :]
    elif url.startswith("http://github.com/"):
        path = url[len("http://github.com/") :]
    elif url.startswith("git@github.com:"):
        path = url[len("git@github.com:") :]
    else:
        raise ValueError(f"Unsupported GitHub remote URL format: {url}")

    # Strip trailing .git and any trailing slash/path.
    path = path.removesuffix(".git")
    if "/" in path:
        parts = path.split("/")
        return f"{parts[0]}/{parts[1]}"
    raise ValueError(f"Could not parse owner/repo from URL: {url}")


def _get_remote_owner_repo(repo_root: Path) -> str:
    """Return 'owner/repo' for the current git remote origin."""
    try:
        remote_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"Could not determine git remote origin: {exc}")

    return _parse_github_owner_repo(remote_url)


def _collect_doc_files(repo_root: Path) -> list[Path]:
    """Return markdown documentation files that might reference the repo URL.

    Note: ARCHIVE/ and .sisyphus/ are excluded. Historical records may
    intentionally reference a previous repo name; they are not treated as
    living documentation.
    """
    globs = [
        repo_root.glob("*.md"),
        repo_root.glob("docs/**/*.md"),
        repo_root.glob(".github/**/*.md"),
    ]
    return sorted(p for paths in globs for p in paths if p.is_file())


class TestDocsWorkflowsBadgeUrl:
    """Ensure docs/workflows.md CI badge points to the canonical git remote."""

    def test_badge_url_matches_git_remote(self) -> None:
        """Parse the CI badge in docs/workflows.md and compare with git remote."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        docs_file = repo_root / "docs" / "workflows.md"
        assert docs_file.exists(), f"Expected docs/workflows.md at {docs_file}"

        # Find the first GitHub Actions badge/workflow URL in the doc and
        # extract the owner/repo from it.
        badge_re = re.compile(r"https://github\.com/([^/]+)/([^/]+)/actions/workflows/[^\s]+?")
        content = docs_file.read_text(encoding="utf-8")
        match = badge_re.search(content)
        assert match, "Could not find a GitHub Actions badge URL in docs/workflows.md"
        badge_owner_repo = f"{match.group(1)}/{match.group(2)}"

        remote_owner_repo = _get_remote_owner_repo(repo_root)
        assert badge_owner_repo == remote_owner_repo, (
            f"docs/workflows.md badge owner/repo ({badge_owner_repo}) does not match "
            f"git remote origin owner/repo ({remote_owner_repo}). Update the badge URL."
        )


class TestDocsRepoUrlDrift:
    """Ensure documentation files that reference the canonical repo URL stay in sync with git remote."""

    def test_doc_repo_urls_under_canonical_owner_match_git_remote(self) -> None:
        """Scan documentation markdown for repo URL drift under the canonical GitHub owner."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        remote_owner_repo = _get_remote_owner_repo(repo_root)
        remote_owner, remote_repo = remote_owner_repo.split("/", 1)

        # Only flag URLs that live under the canonical owner's namespace but point
        # to a repo other than the canonical one. This avoids false positives from
        # unrelated GitHub links (e.g. actions, third-party tools).
        owner_url_re = re.compile(rf"https://github\.com/{re.escape(remote_owner)}/([^/\s]+)")

        mismatches: list[str] = []
        for doc_file in _collect_doc_files(repo_root):
            content = doc_file.read_text(encoding="utf-8")
            for match in owner_url_re.finditer(content):
                repo_name = match.group(1).removesuffix(".git")
                if repo_name != remote_repo:
                    mismatches.append(f"{doc_file}: {match.group(0)}")

        assert not mismatches, (
            "Documentation files contain GitHub repo URLs under the canonical owner "
            f"({remote_owner}) that do not match the git remote origin ({remote_owner_repo}):\n" + "\n".join(mismatches)
        )
