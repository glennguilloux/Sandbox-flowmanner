import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.deps import get_current_user
from app.main_fastapi import app

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-key-123')

# Valid UUID strings for testing
AGENT_ID = '014da489-b7f5-44f7-9e89-046a05a5ab56'
INVALID_AGENT_ID = '00000000-0000-0000-0000-000000000000'


class MockUser:
    def __init__(self, id, email, username, is_active, role):
        self.id = id          # str (matches owner_id type)
        self.email = email
        self.username = username
        self.is_active = is_active
        self.role = role


class MockAgent:
    """Mock that matches AgentResponse schema exactly."""
    def __init__(self, id, name, description, owner_id, model_preference, is_active, is_public):
        self.id = id                      # str (UUID)
        self.name = name
        self.description = description      # str | None
        self.owner_id = owner_id          # str (matches user.id)
        self.model_preference = model_preference  # str | None
        self.is_active = is_active        # bool
        self.is_public = is_public        # bool
        self.system_prompt = ''           # str (not None)
        self.config = None                # str | None
        self.created_at = datetime.now()   # datetime | None
        self.updated_at = datetime.now()  # datetime | None
        self.template_id = None          # str | None


class MockTemplate:
    """Mock that matches AgentTemplateResponse schema exactly."""
    def __init__(self, id, name, description, is_public=True):
        self.id = str(id)                # str (schema requires str)
        self.template_id = 'template_1'  # str (required)
        self.name = name
        self.description = description      # str | None
        self.agent_type = 'custom'        # str (required)
        self.system_prompt = None         # str | None
        self.config_data = {}             # dict | None (matches schema config_data)
        self.is_active = True             # bool | None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()


def make_agent(agent_id=AGENT_ID):
    return MockAgent(
        id=agent_id,
        name='Test Agent',
        description='Test agent for API tests',
        owner_id='1',       # str, matches MockUser.id
        model_preference='gpt-4',
        is_active=True,
        is_public=False,
    )


def make_template():
    return MockTemplate(
        id=1,              # int
        name='Test Template',
        description='Template for testing',
    )


def make_user():
    return MockUser(
        id='1',           # str, matches owner_id
        email='agentuser@example.com',
        username='agentuser',
        is_active=True,
        role='user',
    )


def test_get_agents_success(test_client):
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch('app.api.v1.agent.list_agents', new_callable=AsyncMock) as mock:
            mock.return_value = ([make_agent()], 1)
            response = test_client.get('/api/agents')
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert 'items' in data
            assert len(data['items']) == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_create_agent_success(test_client):
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch('app.api.v1.agent.create_agent', new_callable=AsyncMock) as mock:
            agent = make_agent()
            agent.name = 'New Agent'
            mock.return_value = agent
            response = test_client.post(
                '/api/agents',
                json={'name': 'New Agent', 'description': 'Test', 'model_preference': 'gpt-3.5-turbo'}
            )
            assert response.status_code == 200
            assert response.json()['name'] == 'New Agent'
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_agent_success(test_client):
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch('app.api.v1.agent.require_agent_access', new_callable=AsyncMock) as mock:
            mock.return_value = make_agent()
            response = test_client.get(f'/api/agents/{AGENT_ID}')
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert data['id'] == AGENT_ID
            assert data['owner_id'] == '1'
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_agent_not_found(test_client):
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch('app.api.v1.agent.require_agent_access', new_callable=AsyncMock) as mock:
            mock.side_effect = HTTPException(status_code=404)
            response = test_client.get(f'/api/agents/{INVALID_AGENT_ID}')
            assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_delete_agent_success(test_client):
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch('app.api.v1.agent.get_agent', new_callable=AsyncMock) as get_mock:
            get_mock.return_value = make_agent()
            with patch('app.api.v1.agent.delete_agent', new_callable=AsyncMock) as del_mock:
                del_mock.return_value = True
                response = test_client.delete(f'/api/agents/{AGENT_ID}')
                assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_agent_templates_success(test_client):
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch('app.api.v1.agent.list_agent_templates', new_callable=AsyncMock) as mock:
            mock.return_value = ([make_template()], 1)  # Return (items, total)
            response = test_client.get('/api/agents/templates')
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)
