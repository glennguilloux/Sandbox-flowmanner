#!/usr/bin/env python3
"""
FE<->BE contract drift gate (detective only — never mutates anything).

Why this exists
---------------
Frontend calls backend endpoints that, in several places, do not exist on the
live backend (e.g. /api/votes, /api/subscription/*, /api/swarm/execute). This
script is the CI gate engine: it reconstructs the AUTHORITATIVE backend route
table by importing the live FastAPI app, extracts every /api/* call site from
the frontend source, and fails (exit!=0) on any frontend URL with no matching
backend route.

IMPORTANT constraints (do NOT regen openapi.json — it breaks the VPS-matched SDK):
  - We import the live `app.main_fastapi`, NOT regenerate a spec.
  - Frontend source lives in a SEPARATE repo; pass its path via --frontend (or
    the FE_REPO env). Defaults to /home/glenn/f (symlink to the double-n dir).

Matching rule (avoids the classic ancestor over-match trap):
  A frontend URL is VALID iff, after param-normalization:
    1. it exactly equals a backend route, OR
    2. a backend route is its IMMEDIATE parent (one fewer segment) AND the
       frontend's extra last segment is param-like ({id}, :id, numeric, uuid).
  A backend route that is a *distant* ancestor (e.g. /api/files covering
  /api/files/shared) does NOT validate the child — the missing intermediate
  segment must itself be a real route. This is deliberate.

Usage:
  python3 check_fe_be_contract.py [--frontend PATH] [--src SUBDIR] [--strict]

Exit codes:
  0  no drift
  1  drift found (CI should fail)
  2  environment/usage error
"""
from __future__ import annotations
import argparse
import os
import re
import sys
import importlib

# The backend app imports modules that construct an OpenAI client at import time.
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-contract-gate")
# Quiet noisy third-party init logs.
os.environ.setdefault("OTLP_ENDPOINT", "")
os.environ.setdefault("SANDBOXD_AUTH_TOKEN", "")

BACKEND_APP_IMPORT = "app.main_fastapi"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
URL_RE = re.compile(r"(/api/[^'\"\s`]+)")
# Reject file-path false positives the other agent hit (/api/_mission_cqrs/queries.py)
BAD_EXT_RE = re.compile(r"\.(py|ts|tsx|js|json|md|test)$", re.I)
# Template-literal / comment noise to drop entirely.
NOISE_RE = re.compile(r"[`(),]|/\$\{|\$\{|}|^\.\.\.|\.\.\.$|\.\.\./| \{|\}|\);|\)\s*$")


def sanitize_url(raw: str) -> str | None:
    """Turn a raw regex hit into a clean /api/... path, or None if it is noise."""
    u = raw.strip().strip("`'\",);")
    # strip JS template expressions -> param placeholder
    u = re.sub(r"/\$\{[^}]*\}", "/{x}", u)
    u = re.sub(r"\$\{[^}]*\}", "{x}", u)
    u = u.split("?")[0].split("#")[0]
    u = u.rstrip("/")  # normalize trailing slash (backend has none on most)
    if " " in u or "`" in u or "..." in u:
        return None
    if NOISE_RE.search(u):
        return None
    if not u.startswith("/api/"):
        return None
    if BAD_EXT_RE.search(u):
        return None
    # must be left with only path chars
    if not re.fullmatch(r"/api/[A-Za-z0-9_{}/.\-]*", u):
        return None
    return u


def is_param_seg(seg: str) -> bool:
    if not seg:
        return False
    if seg.startswith("{") or seg.startswith(":"):
        return True
    if seg.isdigit():
        return True
    if UUID_RE.match(seg):
        return True
    return False


def norm_segments(path: str) -> list[str]:
    """Split path into segments, normalize param segments to 'P'."""
    segs = [s for s in path.split("/") if s != ""]
    out = []
    for s in segs:
        out.append("P" if is_param_seg(s) else s)
    return out


def collect_backend_routes() -> set[str]:
    try:
        mod = importlib.import_module(BACKEND_APP_IMPORT)
    except Exception as e:  # pragma: no cover
        print(f"ERROR: cannot import {BACKEND_APP_IMPORT}: {e}", file=sys.stderr)
        sys.exit(2)
    app = getattr(mod, "app", None)
    if app is None:
        print("ERROR: imported module has no 'app'", file=sys.stderr)
        sys.exit(2)
    routes: set[str] = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        if not path or not path.startswith("/api"):
            continue
        routes.add(path)
    return routes


def extract_frontend_urls(frontend_root: str, src_subdir: str) -> list[str]:
    base = os.path.join(frontend_root, src_subdir)
    if not os.path.isdir(base):
        print(f"ERROR: frontend src not found: {base}", file=sys.stderr)
        sys.exit(2)
    urls: list[str] = []
    for root, dirs, files in os.walk(base):
        # skip test trees
        dirs[:] = [d for d in dirs if d != "__tests__" and not d.startswith(".git")]
        for fn in files:
            if not fn.endswith(".ts") or fn.endswith(".test.ts") or ".test." in fn:
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        for m in URL_RE.findall(line):
                            u = sanitize_url(m)
                            if u:
                                urls.append(u)
            except OSError:
                continue
    # dedupe preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def is_valid(fe_norm: list[str], backend_norm: set[tuple[str, ...]]) -> bool:
    # 1. exact match
    if tuple(fe_norm) in backend_norm:
        return True
    # 2. immediate-parent + last segment is param
    if len(fe_norm) >= 2:
        parent = tuple(fe_norm[:-1])
        if parent in backend_norm and is_param_seg(fe_norm[-1].replace("P", "{x}") if fe_norm[-1] == "P" else fe_norm[-1]) or (
            parent in backend_norm and fe_norm[-1] == "P"
        ):
            return True
    return False


def load_allowlist(path: str) -> set[str]:
    allow: set[str] = set()
    if not path or not os.path.isfile(path):
        return allow
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s and not s.startswith("#"):
                allow.add(s)
    return allow


def main() -> int:
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--frontend", default=os.environ.get("FE_REPO", "/home/glenn/f"))
    ap.add_argument("--src", default="src/lib")
    ap.add_argument(
        "--allowlist",
        default=os.path.join(here, "fe_be_contract_known_broken.txt"),
        help="Known-broken URLs to ignore (pre-existing backlog). Fail only on NEW drift.",
    )
    ap.add_argument("--no-allowlist", action="store_true", help="Ignore the allowlist; fail on ANY drift.")
    args = ap.parse_args()

    backend_routes = collect_backend_routes()
    if not backend_routes:
        print("ERROR: backend route table empty", file=sys.stderr)
        sys.exit(2)
    backend_norm = {tuple(norm_segments(r)) for r in backend_routes}

    fe_urls = extract_frontend_urls(args.frontend, args.src)
    if not fe_urls:
        print(f"WARN: no frontend URLs extracted from {args.frontend}/{args.src}", file=sys.stderr)

    allow = set() if args.no_allowlist else load_allowlist(args.allowlist)

    broken: list[str] = []
    for u in fe_urls:
        if is_valid(norm_segments(u), backend_norm):
            continue
        if u in allow:
            continue
        broken.append(u)

    print(f"Backend routes (/api): {len(backend_routes)}")
    print(f"Frontend URLs scanned: {len(fe_urls)}")
    print(f"Known-broken (ignored): {len(allow)}")
    print(f"NEW BROKEN (no backend route, not in allowlist): {len(broken)}")
    print("-" * 60)
    for b in sorted(broken):
        print(b)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
