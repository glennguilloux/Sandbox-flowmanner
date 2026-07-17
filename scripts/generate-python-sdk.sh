#!/usr/bin/env bash
# ============================================================
# generate-python-sdk.sh — Regenerate Python SDK from live OpenAPI spec
# ============================================================
set -euo pipefail

PROJECT_ROOT="/opt/flowmanner"
OPENAPI_SPEC="${PROJECT_ROOT}/openapi.json"
SDK_DIR="${PROJECT_ROOT}/sdk-python"
VENV="${PROJECT_ROOT}/backend/.venv"

echo "=== Python SDK Generation ==="

# Step 1: Generate OpenAPI spec from backend container
# NOTE: importing app.main_fastapi registers middleware that emits a structlog
# JSON line to STDOUT at import time. Dumping the spec to sys.stdout therefore
# prepended that log line, producing a two-document stream ("Extra data" error
# in Step 3). Fix: write the spec to a file INSIDE the container (stdout stays
# clean of the spec), then docker cp it out. The output is exactly one JSON doc.
#
# We also sanitize the spec in-place before writing, for two reasons:
#
#   (a) Enum value de-duplication. A backend enum (MissionStatus) serializes the
#       value "aborted" twice (a deprecated alias maps to the same string), which
#       makes openapi-python-client abort with "Duplicate key ABORTED in enum
#       mission_status.MissionStatus". Dropping the duplicate value
#       (order-preserving) yields the same enum surface without the collision, so
#       the generator succeeds without switching every enum to Literal.
#
#   (b) Schema title disambiguation. openapi-python-client derives each model
#       class name from the schema's "title". Two distinct backend models can
#       share a title (e.g. ModelInfo from app.api.v1.llm and app.schemas.byok,
#       or ShareResponse from app.api.v1.browser and app.api.v1.workspace_shares).
#       When titles collide the generator emits two files with the same name and
#       the LAST one silently clobbers the earlier one, leaving $refs (e.g.
#       BYOKValidateResponse -> app__schemas__byok__ModelInfo) dangling and the
#       referenced schema dropped. We append a stable location-derived
#       suffix to every colliding title so each gets a unique class name
#       while the $ref KEYS (which the generator resolves internally) stay
#       intact. Reference resolution therefore succeeds and no schema is dropped.
echo "[1/3] Generating OpenAPI spec from backend container..."
CONTAINER_SPEC="/tmp/openapi.json"
docker exec backend python -c "
import json, sys, warnings, logging, re
sys.path.insert(0, '/app')
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
from app.main_fastapi import app
spec = app.openapi()

def _dedupe_enums(obj):
    if isinstance(obj, dict):
        enum = obj.get('enum')
        if isinstance(enum, list):
            seen = set(); out = []
            for v in enum:
                key = (type(v).__name__, v)
                if key not in seen:
                    seen.add(key); out.append(v)
            obj['enum'] = out
        for v in obj.values():
            _dedupe_enums(v)
    elif isinstance(obj, list):
        for v in obj:
            _dedupe_enums(v)

def _disambiguate_titles(spec):
    # openapi-python-client derives each model class name from a schema's
    # "title". Two distinct backend models (or two routes that FastAPI exposes
    # as separate paths, e.g. "/api/v2/roadmap" and "/api/v2/roadmap/") can emit
    # schemas that share a title. When titles collide the generator emits two
    # files with the same name and the LAST one silently clobbers the earlier
    # one, leaving \$refs (e.g. BYOKValidateResponse ->
    # app__schemas__byok__ModelInfo) dangling and the referenced schema dropped.
    # We append a stable location-derived suffix to every colliding title so
    # each gets a unique class name while the \$ref KEYS (which the generator
    # resolves internally) stay intact. Reference resolution then succeeds and
    # no schema is dropped.
    #
    # We scan every schema-bearing node: components/schemas (keyed by "title")
    # and inline request/response bodies under paths (keyed by their JSON
    # pointer so two trailing-slash duplicate routes get distinct suffixes).
    from collections import defaultdict

    # Collect (node, loc) for every model-like schema. loc is the components
    # key (e.g. "app__schemas__byok__ModelInfo") or a JSON pointer into paths.
    nodes = []
    schemas = spec.get('components', {}).get('schemas', {})
    for key, val in schemas.items():
        if isinstance(val, dict) and val.get('title'):
            nodes.append((val, key))

    def _walk(obj, ptr, acc):
        if isinstance(obj, dict):
            if 'title' in obj and any(k in obj for k in ('type', 'properties', 'items', 'allOf', 'anyOf', 'oneOf', 'enum')):
                # only treat as a model if it sits under a response/requestBody schema
                if 'responses' in ptr or 'requestBody' in ptr or ptr.endswith('.schema'):
                    acc.append((obj, ptr))
            for k, v in obj.items():
                _walk(v, f'{ptr}.{k}', acc)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _walk(v, f'{ptr}[{i}]', acc)

    _walk(spec.get('paths', {}), 'paths', nodes)

    # Group by the WHITESPACE-NORMALIZED title. openapi-python-client collapses
    # runs of whitespace when deriving a class name, so two schemas whose titles
    # differ only by a double space (e.g. trailing-slash duplicate routes
    # "/api/v2/roadmap" vs "/api/v2/roadmap/") collide on the SAME generated
    # model name even though their raw titles are not byte-identical.
    def _norm(t):
        return re.sub(r'\s+', ' ', t).strip()

    title_to_nodes = defaultdict(list)
    for node, loc in nodes:
        title_to_nodes[_norm(node['title'])].append((node, loc))

    for title, group in title_to_nodes.items():
        if len(group) < 2:
            continue
        # Append a strict index suffix so every colliding title becomes unique
        # regardless of how openapi-python-client sanitizes/truncates it. A JSON
        # pointer suffix normalized away (e.g. the trailing-slash duplicate
        # routes "/api/v2/roadmap" vs "/api/v2/roadmap/" collapse to the same
        # sanitized model name), but an index never does.
        for idx, (node, loc) in enumerate(group, start=2):
            node['title'] = f'{title}_{idx}'

_dedupe_enums(spec)
_disambiguate_titles(spec)
with open('${CONTAINER_SPEC}', 'w') as f:
    json.dump(spec, f, indent=2)
" >/dev/null 2>&1
docker cp "backend:${CONTAINER_SPEC}" "${OPENAPI_SPEC}"
echo "  Spec generated: $(wc -c < "${OPENAPI_SPEC}") bytes"

# Step 1b: Validate the spec is exactly ONE well-formed JSON document with no
# duplicate enum values. This is the regression guard for the two defects this
# script fixed (structlog line prepended to stdout -> "Extra data"; duplicate
# "aborted" in MissionStatus -> "Duplicate key ABORTED"). Before the fix this
# check FAILS (json.load raises "Extra data"); after the fix it PASSES. Failing
# here exits non-zero via set -e, so a regression can never silently reach the
# generator.
echo "  Validating spec is a single well-formed JSON document..."
"${VENV}/bin/python" - "${OPENAPI_SPEC}" <<'PYEOF'
import json, sys, re
from collections import defaultdict
path = sys.argv[1]
with open(path) as f:
    text = f.read()
# json.loads raises "Extra data" if a stray log line preceded the object.
spec = json.loads(text)
assert isinstance(spec, dict) and "openapi" in spec, "spec is not a single OpenAPI object"

def _find_dupe_enums(obj, trail=""):
    dupes = []
    if isinstance(obj, dict):
        enum = obj.get("enum")
        if isinstance(enum, list):
            keys = [(type(v).__name__, v) for v in enum]
            if len(keys) != len(set(keys)):
                dupes.append(obj.get("title") or trail or "<anon>")
        for k, v in obj.items():
            dupes += _find_dupe_enums(v, f"{trail}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            dupes += _find_dupe_enums(v, f"{trail}[{i}]")
    return dupes

def _find_dupe_titles(spec):
    # openapi-python-client derives model class names from schema titles; a
    # duplicate title => two files with the same name => one clobbers the other
    # => dangling $ref => dropped schema (e.g. BYOKValidateResponse). This must
    # therefore include inline response/request-body schemas (where trailing-
    # slash duplicate routes collide), not just components/schemas.
    from collections import defaultdict
    nodes = []
    schemas = spec.get("components", {}).get("schemas", {})
    for val in schemas.values():
        if isinstance(val, dict) and val.get("title"):
            nodes.append(val["title"])
    def _walk(obj, ptr):
        if isinstance(obj, dict):
            if "title" in obj and any(k in obj for k in ("type", "properties", "items", "allOf", "anyOf", "oneOf", "enum")):
                if "responses" in ptr or "requestBody" in ptr or ptr.endswith(".schema"):
                    nodes.append(obj["title"])
            for k, v in obj.items():
                _walk(v, f"{ptr}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _walk(v, f"{ptr}[{i}]")
    _walk(spec.get("paths", {}), "paths")
    # Normalize whitespace: openapi-python-client collapses runs of whitespace
    # when deriving a class name, so titles differing only by spacing collide.
    norm = [re.sub(r'\s+', ' ', t).strip() for t in nodes]
    counts = defaultdict(int)
    for t in norm:
        counts[t] += 1
    return {t: c for t, c in counts.items() if c > 1}

dupes = _find_dupe_enums(spec)
assert not dupes, f"duplicate enum values remain in: {dupes}"

dupe_titles = _find_dupe_titles(spec)
assert not dupe_titles, f"duplicate schema titles remain (model-name collision): {dupe_titles}"

print(f"    OK: single JSON doc, {len(spec.get('paths', {}))} paths, no duplicate enums or titles")
PYEOF

# Step 2: Ensure openapi-python-client is installed
echo "[2/3] Checking openapi-python-client..."
"${VENV}/bin/pip" install -q openapi-python-client 2>/dev/null || {
  echo "  Installing openapi-python-client..."
  "${VENV}/bin/pip" install openapi-python-client
}
echo "  openapi-python-client ready"

# Step 3: Generate Python SDK
echo "[3/3] Generating Python SDK..."
cd "${SDK_DIR}"
"${VENV}/bin/openapi-python-client" generate --path "${OPENAPI_SPEC}" --output-path . --overwrite
echo "  Python SDK generated"

echo "=== Python SDK generation complete ==="
