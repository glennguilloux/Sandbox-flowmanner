"""Unit tests for FlowmannerClient high-level wrapper.

Tests use httpx.MockTransport to intercept HTTP requests without hitting a real server.
"""

from __future__ import annotations

import json

import httpx
import pytest

from flowmanner_api_client.high_level import FlowmannerClient

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure FLOWMANNER_API_KEY doesn't leak between tests."""
    monkeypatch.delenv("FLOWMANNER_API_KEY", raising=False)


def _mock_transport(handler):
    """Create a mock httpx transport that routes requests to *handler*."""
    return httpx.MockTransport(handler)


def _json_response(data, status_code=200):
    """Helper to create a JSON httpx.Response."""
    return httpx.Response(status_code, json=data)


def _ok_handler(calls: list):
    """Generic handler that records requests and returns {\"ok\": true}."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "json": json.loads(request.content) if request.content else None,
            }
        )
        return _json_response({"ok": True})

    return handler


# ── Constructor tests ───────────────────────────────────────────────────────


class TestConstructor:
    def test_init_with_api_key(self):
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test")
        assert client.base_url == "https://example.com"
        assert client._api_key == "sk-test"

    def test_init_strips_trailing_slash(self):
        client = FlowmannerClient(base_url="https://example.com/", api_key="sk-test")
        assert client.base_url == "https://example.com"

    def test_init_from_env_var(self, monkeypatch):
        monkeypatch.setenv("FLOWMANNER_API_KEY", "sk-env")
        client = FlowmannerClient(base_url="https://example.com")
        assert client._api_key == "sk-env"

    def test_init_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("FLOWMANNER_API_KEY", raising=False)
        with pytest.raises(ValueError, match="API key required"):
            FlowmannerClient(base_url="https://example.com")

    def test_explicit_key_overrides_env(self, monkeypatch):
        monkeypatch.setenv("FLOWMANNER_API_KEY", "sk-env")
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-explicit")
        assert client._api_key == "sk-explicit"

    def test_custom_timeout(self):
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test", timeout=60)
        # Verify the client was created (timeout is passed to httpx)
        assert client._client is not None


# ── Context manager tests ───────────────────────────────────────────────────


class TestContextManager:
    def test_context_manager_enter_returns_self(self):
        calls = []
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test")
        # Replace transport so the real httpx client uses our mock
        client._client.set_httpx_client(
            httpx.Client(
                transport=_mock_transport(_ok_handler(calls)),
                base_url="https://example.com",
            )
        )
        with client as fm:
            assert fm is client

    def test_context_manager_exit_works(self):
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test")
        client._client.set_httpx_client(
            httpx.Client(
                transport=_mock_transport(lambda r: _json_response({})),
                base_url="https://example.com",
            )
        )
        with client:
            pass  # should not raise


# ── Mission CRUD tests ──────────────────────────────────────────────────────


class TestMissions:
    def _make_client(self, handler):
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test")
        client._client.set_httpx_client(
            httpx.Client(transport=_mock_transport(handler), base_url="https://example.com")
        )
        return client

    def test_create_mission(self):
        calls = []
        client = self._make_client(_ok_handler(calls))
        result = client.create_mission(title="Test", description="Desc", mission_type="research", priority="high")
        assert result == {"ok": True}
        assert len(calls) == 1
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/missions"
        assert calls[0]["json"]["title"] == "Test"
        assert calls[0]["json"]["description"] == "Desc"
        assert calls[0]["json"]["mission_type"] == "research"
        assert calls[0]["json"]["priority"] == "high"

    def test_create_mission_defaults(self):
        calls = []
        client = self._make_client(_ok_handler(calls))
        client.create_mission(title="Simple")
        assert calls[0]["json"]["mission_type"] == "general"
        assert calls[0]["json"]["priority"] == "medium"
        assert calls[0]["json"]["description"] == ""

    def test_get_mission(self):
        mission_data = {"id": "abc-123", "status": "completed", "title": "Test"}

        def handler(request):
            return _json_response(mission_data)

        client = self._make_client(handler)
        result = client.get_mission("abc-123")
        assert result == mission_data

    def test_list_missions(self):
        missions = [{"id": "1"}, {"id": "2"}]
        calls = []

        def handler(request):
            calls.append({"path": request.url.path, "params": dict(request.url.params)})
            return _json_response(missions)

        client = self._make_client(handler)
        result = client.list_missions(limit=5, status="completed")
        assert result == missions
        assert calls[0]["params"]["limit"] == "5"
        assert calls[0]["params"]["status"] == "completed"

    def test_list_missions_no_status(self):
        calls = []
        client = self._make_client(_ok_handler(calls))
        client.list_missions(limit=10)
        assert "status" not in calls[0]["params"]
        assert calls[0]["params"]["limit"] == "10"

    def test_execute_mission(self):
        calls = []
        client = self._make_client(_ok_handler(calls))
        result = client.execute_mission("abc-123")
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/missions/abc-123/execute"

    def test_execute_mission_async(self):
        calls = []
        client = self._make_client(_ok_handler(calls))
        client.execute_mission_async("abc-123")
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/api/v1/missions/abc-123/execute-async"

    def test_get_mission_status(self):
        def handler(request):
            return _json_response({"id": "abc", "status": "running"})

        client = self._make_client(handler)
        assert client.get_mission_status("abc") == "running"

    def test_get_mission_status_missing_key(self):
        def handler(request):
            return _json_response({"id": "abc"})

        client = self._make_client(handler)
        assert client.get_mission_status("abc") == "unknown"

    def test_delete_mission(self):
        calls = []
        client = self._make_client(_ok_handler(calls))
        client.delete_mission("abc-123")
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/api/v1/missions/abc-123"


# ── Tasks & Logs tests ──────────────────────────────────────────────────────


class TestTasksAndLogs:
    def _make_client(self, handler):
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test")
        client._client.set_httpx_client(
            httpx.Client(transport=_mock_transport(handler), base_url="https://example.com")
        )
        return client

    def test_list_tasks(self):
        tasks = [{"id": "t1", "title": "Task 1"}]

        def handler(request):
            assert request.url.path == "/api/v1/missions/abc/tasks"
            return _json_response(tasks)

        client = self._make_client(handler)
        assert client.list_tasks("abc") == tasks

    def test_list_logs(self):
        logs = [{"id": "l1", "message": "started"}]

        def handler(request):
            assert request.url.path == "/api/v1/missions/abc/logs"
            return _json_response(logs)

        client = self._make_client(handler)
        assert client.list_logs("abc") == logs


# ── Analytics tests ─────────────────────────────────────────────────────────


class TestAnalytics:
    def _make_client(self, handler):
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test")
        client._client.set_httpx_client(
            httpx.Client(transport=_mock_transport(handler), base_url="https://example.com")
        )
        return client

    def test_get_usage_summary(self):
        calls = []
        summary = {"total_tokens": 1000, "total_cost": 0.05}

        def handler(request):
            calls.append({"path": request.url.path, "params": dict(request.url.params)})
            return _json_response(summary)

        client = self._make_client(handler)
        result = client.get_usage_summary(period="7d")
        assert result == summary
        assert calls[0]["path"] == "/api/v1/usage/summary"
        assert calls[0]["params"]["period"] == "7d"

    def test_get_usage_summary_default_period(self):
        calls = []
        client = self._make_client(_ok_handler(calls))
        client.get_usage_summary()
        assert calls[0]["params"]["period"] == "30d"

    def test_get_cost_analytics(self):
        calls = []
        client = self._make_client(_ok_handler(calls))
        client.get_cost_analytics(period="week")
        assert calls[0]["path"] == "/api/v2/dashboard/costs"
        assert calls[0]["params"]["period"] == "week"


# ── System tests ────────────────────────────────────────────────────────────


class TestSystem:
    def _make_client(self, handler):
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test")
        client._client.set_httpx_client(
            httpx.Client(transport=_mock_transport(handler), base_url="https://example.com")
        )
        return client

    def test_health_check(self):
        def handler(request):
            assert request.url.path == "/api/health"
            return _json_response({"status": "healthy"})

        client = self._make_client(handler)
        assert client.health_check() == {"status": "healthy"}

    def test_list_agents(self):
        agents = [{"id": "a1", "name": "Research Agent"}]

        def handler(request):
            return _json_response(agents)

        client = self._make_client(handler)
        assert client.list_agents() == agents

    def test_get_agent(self):
        agent = {"id": "a1", "name": "Research Agent"}

        def handler(request):
            assert request.url.path == "/api/v1/agents/a1"
            return _json_response(agent)

        client = self._make_client(handler)
        assert client.get_agent("a1") == agent


# ── Error handling tests ────────────────────────────────────────────────────


class TestErrorHandling:
    def _make_client(self, handler):
        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test")
        client._client.set_httpx_client(
            httpx.Client(transport=_mock_transport(handler), base_url="https://example.com")
        )
        return client

    def test_404_raises(self):
        def handler(request):
            return httpx.Response(404, json={"detail": "Not found"})

        client = self._make_client(handler)
        with pytest.raises(httpx.HTTPStatusError):
            client.get_mission("nonexistent")

    def test_500_raises(self):
        def handler(request):
            return httpx.Response(500, json={"detail": "Internal error"})

        client = self._make_client(handler)
        with pytest.raises(httpx.HTTPStatusError):
            client.health_check()

    def test_401_raises(self):
        def handler(request):
            return httpx.Response(401, json={"detail": "Unauthorized"})

        client = self._make_client(handler)
        with pytest.raises(httpx.HTTPStatusError):
            client.list_missions()

    def test_422_raises(self):
        def handler(request):
            return httpx.Response(422, json={"detail": [{"msg": "field required"}]})

        client = self._make_client(handler)
        with pytest.raises(httpx.HTTPStatusError):
            client.create_mission(title="")


# ── Auth header tests ───────────────────────────────────────────────────────


class TestAuthHeader:
    def test_auth_header_sent(self):
        captured_headers = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return _json_response({"ok": True})

        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test-123")
        # AuthenticatedClient sets auth header lazily in get_httpx_client().
        # After construction, get_httpx_client() will have the header wired up.
        # We then swap the transport on the existing client to intercept requests.
        real_client = client._client.get_httpx_client()
        # Close the real transport and replace with mock
        real_client._transport = _mock_transport(handler)
        client.health_check()
        assert "authorization" in captured_headers
        assert captured_headers["authorization"] == "Bearer sk-test-123"

    def test_get_without_params(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["params"] = dict(request.url.params)
            captured["path"] = request.url.path
            return _json_response({"status": "healthy"})

        client = FlowmannerClient(base_url="https://example.com", api_key="sk-test")
        client._client.set_httpx_client(
            httpx.Client(transport=_mock_transport(handler), base_url="https://example.com")
        )
        result = client.health_check()
        assert result == {"status": "healthy"}
        assert captured["path"] == "/api/health"
        # health_check passes no params
        assert captured["params"] == {}
