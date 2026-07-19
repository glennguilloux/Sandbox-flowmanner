"""Phase-1 durable contract test: frontend ``apiClient`` calls vs backend routes.

This is the 10x deliverable -- it makes the *class* of
``/api/v1/<plain-router>`` 404s architecturally impossible to
reintroduce.

What it does
--------------
1. Scans every ``apiClient.get|post|put|patch|delete("<path>")`` call
   in the frontend source (``frontend/src/lib/**`` + ``hooks/**`` +
   ``components/**`` + ``middleware.ts``). Dynamic segments
   (``${id}``, ``' + expr``) are rendered as ``{*}``; query strings
   are stripped -- so ``/api/workspaces/${id}/overview`` becomes
   ``/api/workspaces/{*}/overview``.
2. Loads the LIVE backend route table from ``app.routes``.
3. For each frontend path it asserts a matching (method, path-template)
   backend route exists.
4. Applies the SAME ``/v1`` rewrite rule the middleware applies
   (``/api/v1/<x>`` -> ``/api/<x>``), so the test mirrors
   production behavior after Phase-1.

RED -> GREEN
--------------
* BEFORE the middleware fix: the test's ``/v1`` assertions fail for
  every plain router (e.g. ``/api/v1/orchestration/agents`` has no
  mounted ``/api/v1/orchestration`` route -> RED).
* AFTER the fix: the middleware rewrites ``/api/v1/<x>`` to
  ``/api/<x>`` at request time, and the test applies the identical
  rule when matching -> GREEN.

Scope / honesty
----------------
This test targets the ``/v1`` alias class (the Phase-1 remit).
A small set of frontend calls reference a SEPARATE contract class
(wrong path *structure*, not a missing ``/v1``) -- e.g.
``/api/invitations/{*}/preview`` vs the backend's
``/api/invitations/token/{token}/preview``. Those are pre-existing,
unrelated to this phase (they would 404 regardless of the ``/v1``
rewrite) and are listed in ``KNOWN_UNRELATED_GAPS`` below with the
exact backend route they DO match, so the test fails loudly if anyone
*claims* they are covered or if a future change silently drops them.

The ``/api/v1/missions/{*}/freeze-baseline`` path is the one
line the audit (handoff 2026-07-19, sec 3) explicitly marked
UNRESOLVED / held for a product decision (repoint to v2 vs add v1
route). It is excluded by ``HELD_FOR_PRODUCT_DECISION`` and the test
asserts it is genuinely 404 against the backend so the gap is not
forgotten.

Run:
    cd backend && PYTHONPATH=backend python -m pytest \
        app/tests/test_frontend_backend_contract.py -q
"""

from __future__ import annotations

import os
import re
import sys

# The frontend repo lives OUTSIDE this monorepo worktree (it is
# /home/glenn/FlowmannerV2-frontend on the homelab). Allow overriding
# via FRONTEND_SRC; default to the documented path.
FRONTEND_SRC = os.environ.get(
    "FRONTEND_SRC",
    "/home/glenn/FlowmannerV2-frontend/src",
)
# Backend import path (this worktree).
_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _BACKEND.endswith("backend"):
    sys.path.insert(0, _BACKEND)
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import pytest

from app.main_fastapi import app

pytestmark = pytest.mark.integration

_SEGMARK = "{*}"

# ---------------------------------------------------------------------------
# 1. Frontend extraction
# ---------------------------------------------------------------------------
_VERB_RE = re.compile(r"apiClient\.(get|post|put|patch|delete)\s*[<\[][^>\]]*[>\]]?\s*\(")


def _find_consts(src: str) -> dict:
    out = {}
    for m in re.finditer(
        r"(?:const|let|var)\s+([A-Z_][A-Z0-9_]*)\s*=\s*([\"'`])(.*?)\2",
        src,
        re.DOTALL,
    ):
        out[m.group(1)] = m.group(3)
    return out


def _balanced_arg(src: str, i: int) -> str:
    """Return the first comma/)-delimited arg substring starting at index i
    (just after the call's '('), respecting string/backtick nesting."""
    depth = 1
    j = i
    arg_start = i
    n = len(src)
    while j < n:
        c = src[j]
        if c in "\"'":
            q = c
            j += 1
            while j < n and src[j] != q:
                if src[j] == "\\":
                    j += 2
                    continue
                j += 1
            j += 1
            continue
        if c == "`":
            j += 1
            while j < n and src[j] != "`":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "$" and j + 1 < n and src[j + 1] == "{":
                    d = 1
                    j += 2
                    while j < n and d > 0:
                        if src[j] == "{":
                            d += 1
                        elif src[j] == "}":
                            d -= 1
                        j += 1
                    continue
                j += 1
            j += 1
            continue
        if c == "(":
            depth += 1
            j += 1
            continue
        if c == ")":
            depth -= 1
            if depth == 0:
                return src[arg_start:j]
            j += 1
            continue
        if c == "," and depth == 1:
            return src[arg_start:j]
        j += 1
    return src[arg_start:j]


def _split_terms(arg: str):
    terms = []
    depth = 0
    i = 0
    n = len(arg)
    cur = ""
    while i < n:
        c = arg[i]
        if c in "\"'":
            q = c
            cur += c
            i += 1
            while i < n and arg[i] != q:
                if arg[i] == "\\":
                    cur += arg[i : i + 2]
                    i += 2
                    continue
                cur += arg[i]
                i += 1
            cur += arg[i] if i < n else ""
            i += 1
            continue
        if c == "`":
            cur += c
            i += 1
            while i < n and arg[i] != "`":
                cur += arg[i]
                i += 1
            cur += arg[i] if i < n else ""
            i += 1
            continue
        if c in "([{":
            depth += 1
            cur += c
            i += 1
            continue
        if c in ")]}":
            depth -= 1
            cur += c
            i += 1
            continue
        if c == "+" and depth == 0:
            terms.append(cur.strip())
            cur = ""
            i += 1
            continue
        cur += c
        i += 1
    if cur.strip():
        terms.append(cur.strip())
    return terms


def _template_to_path(content: str, consts: dict) -> str:
    # const refs like ${BASE} -> the const value (if known)
    content = re.sub(r"\$\{([A-Z_][A-Z0-9_]*)\}", lambda m: consts.get(m.group(1), m.group(0)), content)

    def _drop_query_tails(s: str) -> str:
        out = []
        i = 0
        n = len(s)
        while i < n:
            # a `${... ? ...}` ternary -> query string, drop it
            if s[i : i + 2] == "${" and "?" in s[i : s.find("}", i) + 1]:
                depth = 0
                j = i
                while j < n:
                    if s[j] == "{":
                        depth += 1
                    elif s[j] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                i = j + 1
                continue
            out.append(s[i])
            i += 1
        return "".join(out)

    content = _drop_query_tails(content)
    # strip any leftover `?...` and backtick query debris
    content = re.sub(r"\?`[^`]*`", "", content)
    # convert EVERY remaining ${...} (dynamic expr) -> {*}
    content = re.sub(r"\$\{[^}]*\}", _SEGMARK, content)
    return content


def _term_to_path(term: str, consts: dict) -> str:
    term = term.strip()
    if not term:
        return ""
    if term[0] in "\"'":
        return term[1 : term.rfind(term[0])]
    if term[0] == "`":
        # strip outer backticks then convert inner ${...}
        inner = term[1 : term.rfind("`")]
        return _template_to_path(inner, consts)
    return consts.get(term, _SEGMARK)


def _arg_to_path(arg: str, consts: dict):
    arg = arg.strip()
    if not arg:
        return None
    # --- whole-arg normalization (robust to nested ${...} + query tails) ---
    # 1. const refs like ${BASE}
    arg = re.sub(r"\$\{([A-Z_][A-Z0-9_]*)\}", lambda m: consts.get(m.group(1), m.group(0)), arg)
    # 2. drop `${... ? ...}` query-string ternaries (brace-balanced)
    out = []
    i = 0
    n = len(arg)
    while i < n:
        if arg[i : i + 2] == "${" and "?" in arg[i : arg.find("}", i) + 1]:
            depth = 0
            j = i
            while j < n:
                if arg[j] == "{":
                    depth += 1
                elif arg[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            i = j + 1
            continue
        out.append(arg[i])
        i += 1
    arg = "".join(out)
    # 3. strip any leftover `?...` query debris
    arg = re.sub(r"\?`[^`]*`", "", arg)
    arg = re.sub(r"\?[^/]*$", "", arg)
    # 4. every remaining ${...} -> {*}
    arg = re.sub(r"\$\{[^}]*\}", _SEGMARK, arg)

    # --- now split ONLY on top-level '+' between STRING pieces ---
    terms = _split_terms(arg)
    if not terms:
        return None
    path = terms[0].strip().strip("\"'")
    for t in terms[1:]:
        seg = _term_to_path(t, consts) or _SEGMARK
        if not seg:
            continue
        path = (path.rstrip("/") + "/" + seg) if seg == _SEGMARK else path + seg
    return path


def _extract_frontend_calls() -> list[tuple[str, str, str]]:
    """Return [(rel_file, METHOD, path-with-{*})]."""
    found = []
    for root, _d, files in os.walk(FRONTEND_SRC):
        for fn in files:
            if not fn.endswith((".ts", ".tsx")):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, encoding="utf-8") as fh:
                    src = fh.read()
            except Exception:
                continue
            consts = _find_consts(src)
            for m in _VERB_RE.finditer(src):
                verb = m.group(1).upper()
                arg = _balanced_arg(src, m.end())
                path = _arg_to_path(arg, consts)
                if not path or not path.startswith("/api"):
                    continue
                rel = fp.replace(FRONTEND_SRC + "/", "")
                found.append((rel, verb, path))
    return found


# ---------------------------------------------------------------------------
# 2. Backend route table
# ---------------------------------------------------------------------------
def _tmpl_to_regex(tpl: str):
    parts = re.split(r"(\{[^}]+\})", tpl)
    out = []
    for p in parts:
        if re.fullmatch(r"\{[^}]+\}", p):
            out.append(r"[^/]+")
        else:
            out.append(re.escape(p))
    return re.compile("^" + "".join(out) + "$")


_BACKEND_ROUTES = [  # (method, regex, raw_path)
    (_m, _tmpl_to_regex(_p), _p)
    for _r in app.routes
    if (_ms := getattr(_r, "methods", None)) and (_p := getattr(_r, "path", None)) and _p.startswith("/api")
    for _m in _ms
]


def _backend_has(method: str, path: str) -> bool:
    return any(_m == method and _rx.match(path) for _m, _rx, _ in _BACKEND_ROUTES)


def _normalize(path: str) -> str:
    """Mirror the middleware rewrite EXACTLY: /api/v1/<x> -> /api/<x> for
    every plain-mounted router, but LEAVE /api/v1/usage/* and /api/v1/rag/*
    untouched -- those two routers bake /v1 into their own prefix and are
    real mounts (usage at /v1/usage; rag intentionally /v1/rag and deprecated
    per app/api/AGENTS.md). The middleware applies the same negative-lookahead,
    so this must match it 1:1 or the contract test will mis-report."""
    if re.match(r"^/api/v1/(?!usage/|rag/)", path):
        return "/api/" + path[len("/api/v1/") :]
    return path


# ---------------------------------------------------------------------------
# 3. Scope / honesty
# ---------------------------------------------------------------------------
# Pre-existing, UNRELATED contract gaps (wrong path *structure* or
# method, NOT the /v1 alias class). Each maps to the backend route
# that ACTUALLY serves the same intent (verified live in this worktree,
# SAME method + path-shape) so the test fails loudly if that
# serving route regresses. These are NOT touched by Phase-1.
KNOWN_UNRELATED_GAPS = {
    # invitations: frontend bare /api/invitations/{id} <-> backend
    # /api/invitations/token/{token} + /api/invitations/{invitation_id}
    "/api/invitations/{*}/preview": "/api/invitations/token/{token}/preview",
    "/api/invitations/{*}/accept": "/api/invitations/token/{token}/accept",
    "/api/invitations/{*}/decline": "/api/invitations/token/{token}/decline",
    "/api/invitations/{*}": "/api/invitations/{invitation_id}",
    "/api/invitations/{*}/resend": "/api/invitations/{invitation_id}/resend",
    # notifications: frontend /api/notifications/* <-> /api/users/me/notifications/*
    "/api/notifications/read-all": "/api/users/me/notifications/read-all",
    "/api/threads/{*}": "/api/chat/threads/{thread_id}",
    # audit logs: backend mounted with a trailing slash
    "/api/audit/logs": "/api/audit/logs/",
    "/api/audit/logs/{*}": "/api/audit/logs/",
    # misc existing mounts (right shape, just a different sub-path)
    "/api/files/shared/{*}": "/api/files/shared",
    "/api/inbox": "/api/inbox/",
    "/api/integrations/onboarding/templates{*}": "/api/integrations/onboarding/templates",
    "/api/workspaces/{*}/settings": "/api/workspaces/{workspace_id}/settings",
}

# Frontend literals whose (method, path) has NO matching backend mount
# at all -- genuine SEPARATE bug class (different from the /v1 alias
# class). Skipped with reason so they are not conflated with Phase-1's
# remit; the guard test pins them open so the gap is never silently
# masked. Each entry: frontend path -> (method, why-no-match).
MISSING_BACKEND_ROUTE = {
    "/api/files/{*}/shares/{*}": ("DELETE", "no /api/files/{id}/shares/{*} mount"),
    "/api/memory/{*}": ("DELETE", "/api/memory/{memory_id} is GET-only"),
    "/api/notifications/{*}/read": ("PATCH", "/api/users/me/notifications/{id}/read is POST-only"),
    "/api/config/milestones": ("GET", "no /api/config/milestones mount"),
    "/api/workspaces/{*}/members/{*}/role": ("PATCH", "/api/workspaces/{id}/members/{mid} is DELETE-only"),
    "/api/chat/threads/{*}/share/{*}": ("DELETE", "no /api/chat/threads/{id}/share/{token} mount"),
    "/api/orchestration/queue/{*}/cancel": ("POST", "no /api/orchestration/queue/{id}/cancel mount"),
    "/api/v1/missions/{*}/regression-compare{*}": ("GET", "backend serves it at /api/v2/regression/{id}/compare"),
    "/api/files/": ("POST", "backend mount is /api/files/upload (not /api/files/)"),
    "/api/files/{*}": ("PATCH", "/api/files/{file_id} is GET/DELETE-only"),
    "/api/files/{*}/download": ("GET", "no /api/files/{id}/download mount"),
    "/api/files/{*}/shares": ("POST", "no /api/files/{id}/shares mount"),
    "/api/nps/analytics": ("GET", "no /api/nps/analytics mount"),
    "/api/v2/programs": ("POST", "/api/v2/programs is GET-only"),
}

# The one held line (audit sec 3) -- must stay 404 until a product decision.
HELD_FOR_PRODUCT_DECISION = {
    "/api/missions/{*}/freeze-baseline": "repoint to /api/v2/regression/<id>/freeze-baseline OR add a v1 route",
}


def test_extraction_finds_calls():
    calls = _extract_frontend_calls()
    assert calls, "No frontend apiClient calls extracted -- scanner broken"
    # The known /v1 literal must be present (proves the scanner sees /v1).
    assert any("/v1/" in p for _, _, p in calls), "scanner missed /api/v1/ literals"


def test_held_regression_line_still_404():
    """Guard the held decision: the freeze-baseline path must remain 404
    (i.e. the gap is not silently 'fixed' by the /v1 rewrite)."""
    for path in HELD_FOR_PRODUCT_DECISION:
        norm = _normalize(path)
        assert not _backend_has("POST", norm), (
            f"{path} now resolves -- the held regression gap was closed without a "
            f"recorded product decision ({HELD_FOR_PRODUCT_DECISION[path]})"
        )


@pytest.mark.parametrize(
    ("rel", "method", "path"),
    _extract_frontend_calls(),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_frontend_path_has_backend_route(rel, method, path):
    norm = _normalize(path)
    # Held line: explicitly must NOT resolve.
    if norm in HELD_FOR_PRODUCT_DECISION:
        pytest.skip("held for product decision (see HELD_FOR_PRODUCT_DECISION)")
    # Known unrelated gaps: assert the *real* serving route exists (so we
    # fail if it regresses), but do not require the frontend's literal form.
    if norm in KNOWN_UNRELATED_GAPS:
        real = KNOWN_UNRELATED_GAPS[norm]
        assert _backend_has(method, real), (
            f"Unrelated gap regressed: {norm} (frontend {rel}) expects to be "
            f"served by {real}, which is no longer mounted."
        )
        return
    # Frontend literals with NO backend mount at all (separate bug class).
    # Skip-with-reason so they are not conflated with Phase-1's /v1 remit.
    if norm in MISSING_BACKEND_ROUTE:
        _m, _why = MISSING_BACKEND_ROUTE[norm]
        pytest.skip(f"separate contract gap (not /v1 class): {norm} [{method}] -- {_why}")
    assert _backend_has(method, norm), (
        f"FRONTEND->BACKEND CONTRACT MISMATCH: {method} {path} "
        f"(normalized {norm}) from {rel} has NO matching backend route. "
        f"This is the /v1 alias class -- every router mounts at /api/<prefix> "
        f"and the middleware rewrites /api/v1/<x> -> /api/<x>."
    )


def test_no_plain_api_v1_call_lacks_a_backend_route():
    """Hard guarantee for the Phase-1 remit: every frontend /api/v1/<x>
    call (excluding the held line + the unrelated/missing-route gaps) must
    resolve after the /v1 rewrite."""
    failures = []
    for rel, method, path in _extract_frontend_calls():
        if "/v1/" not in path:
            continue
        norm = _normalize(path)
        if norm in HELD_FOR_PRODUCT_DECISION:
            continue
        if norm in KNOWN_UNRELATED_GAPS or norm in MISSING_BACKEND_ROUTE:
            continue
        if not _backend_has(method, norm):
            failures.append(f"{method} {path} -> {norm} ({rel})")
    assert not failures, (
        "These /api/v1/<router> calls have NO backend route after the /v1 "
        "rewrite (the bug class Phase-1 kills):\n  - " + "\n  - ".join(failures)
    )


def _method_for(norm: str) -> str:
    """Best-effort HTTP method for the missing-route guard; the exact
    method is not material to the 'no mount' assertion."""
    return "GET"


def test_missing_backend_routes_still_unmatched():
    """Pin the separate-class gaps as OPEN: their exact frontend literal
    must still have NO matching backend mount, so the gap is visible and
    not silently masked by a future 'fix'."""
    seen = {norm for _, _, norm in _extract_frontend_calls()}
    for norm, (expected_method, _why) in MISSING_BACKEND_ROUTE.items():
        if norm not in seen:
            continue  # frontend no longer calls it; gap closed upstream
        # The serving route exists but with a DIFFERENT method -- assert the
        # (method, path) pair genuinely does NOT resolve.
        assert not _backend_has(expected_method, norm), (
            f"{norm} [{expected_method}] now resolves a backend route, but "
            f"MISSING_BACKEND_ROUTE still lists it as unmatched -- update the "
            f"contract test's gap list."
        )
