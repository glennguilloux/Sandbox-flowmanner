"""Tests for the agent-personalities API (scan-root + filters).

The loader reads markdown files from the entire ``agent_definitions/`` tree.
There are 215 persona files on disk across 16 domain directories (some nested
one level deeper, e.g. ``game-development/unity/...``). The endpoint must
surface all of them.
"""

from app.api.v1 import agent_personalities as ap


def test_loads_all_215_personalities():
    personalities = ap._load_all_personalities()
    assert len(personalities) == 215


def test_all_personalities_have_unique_ids():
    personalities = ap._load_all_personalities()
    ids = [p["id"] for p in personalities]
    assert len(ids) == len(set(ids))


def test_surfaces_all_16_domains():
    personalities = ap._load_all_personalities()
    domains = {p["domain"] for p in personalities}
    assert len(domains) == 16


def test_list_supports_domain_filter():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(ap.router)
    client = TestClient(app)

    resp = client.get("/agent-personalities?domain=engineering")
    assert resp.status_code == 200
    body = resp.json()
    assert body, "expected at least one engineering persona"
    assert all(p["domain"] == "engineering" for p in body)


def test_list_supports_q_filter():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(ap.router)
    client = TestClient(app)

    resp = client.get("/agent-personalities?q=review")
    assert resp.status_code == 200
    body = resp.json()
    assert body, "expected at least one match for 'review'"
    needle = "review"
    assert all(
        needle in p["name"].lower() or needle in p["description"].lower() for p in body
    )


def test_get_nested_personality_by_id():
    personalities = ap._load_all_personalities()
    nested = next(p for p in personalities if p["id"].count("/") > 1)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(ap.router)
    client = TestClient(app)

    resp = client.get(f"/agent-personalities/{nested['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == nested["id"]
