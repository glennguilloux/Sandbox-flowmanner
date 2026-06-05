# LangGraph Agent

An intelligent workflow automation agent built with LangGraph that provides natural language to tool conversion, human approval workflows, and tool persistence.

## Features

- **Natural Language to Tool Conversion**: Converts user requests into structured tool calls using LLM
- **Human Approval Workflow**: Manages approval requests for tool execution with configurable policies
- **Tool Persistence**: Saves and reuses tool configurations across sessions
- **State Management**: Maintains conversation state and tool execution history
- **Session Management**: Persistent sessions with Redis caching
- **Extensible Architecture**: Easy to add new tools and handlers

## Architecture

### Components

1. **State Management** ([`state.py`](state.py))
   - `AgentState`: Main state schema for the agent
   - `ToolExecution`: Represents a tool execution request
   - `ConversationMessage`: Represents a message in the conversation

2. **Tool Converter** ([`tool_converter.py`](tool_converter.py))
   - `ToolConverter`: Converts natural language to tool calls
   - `ToolDefinition`: Represents a tool with schema
   - Includes default tools for n8n, ComfyUI, 3Dglenn, and more

3. **Approval Workflow** ([`approval_workflow.py`](approval_workflow.py))
   - `ApprovalWorkflow`: Manages human approval for tool execution
   - `ApprovalRequest`: Represents an approval request
   - Auto-approval for safe tools

4. **Persistence** ([`persistence.py`](persistence.py))
   - `AgentPersistence`: Handles state and configuration persistence
   - Redis-based caching for sessions
   - Tool configuration management

5. **Agent** ([`agent.py`](agent.py))
   - `LangGraphAgent`: Main agent orchestrating all components
   - LangGraph state machine for workflow execution
   - Tool execution handlers

## Installation

```bash
pip install -r requirements-langgraph.txt
```

## Configuration

Environment variables:

```bash
# Redis (required for persistence)
REDIS_URL=redis://localhost:6379

# LLM (optional, for tool conversion)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=phi3:3.8b

# Approval settings
AUTO_APPROVE_SAFE_TOOLS=true
REQUIRE_APPROVAL_FOR_ALL=false
```

## Usage

### Basic Chat

```python
from app.services.langgraph import get_agent

agent = get_agent()

result = await agent.process_message(
    message="Execute the n8n workflow for image generation",
    session_id="my_session",
    user_id=1,
)

print(result["response"])
```

### Handling Approvals

```python
# User approves a tool execution
result = await agent.handle_approval(
    session_id="my_session",
    action="approve",
    user_id=1,
)
```

### Saving Tool Configurations

```python
from app.services.langgraph import get_persistence

persistence = get_persistence()

config_id = persistence.save_tool_configuration(
    user_id=1,
    tool_id="execute_comfyui_workflow",
    tool_name="Execute ComfyUI Workflow",
    name="My Image Config",
    description="Default settings for image generation",
    parameters={
        "workflow_id": "workflow_123",
        "prompt": "A beautiful landscape",
        "width": 1024,
        "height": 1024,
    },
)
```

### Loading Saved Configurations

```python
configs = persistence.list_user_configurations(user_id=1)
for config in configs:
    print(f"{config['name']}: {config['description']}")
```

## API Endpoints

### Chat

```http
POST /api/langgraph/chat
Content-Type: application/json

{
  "message": "Execute the n8n workflow",
  "session_id": "optional_session_id",
  "context": {}
}
```

### Approval

```http
POST /api/langgraph/approval
Content-Type: application/json

{
  "session_id": "session_id",
  "action": "approve",
  "reason": "optional reason"
}
```

### List Tools

```http
GET /api/langgraph/tools?category=workflow
```

### Save Configuration

```http
POST /api/langgraph/configs
Content-Type: application/json

{
  "tool_id": "execute_comfyui_workflow",
  "tool_name": "Execute ComfyUI Workflow",
  "name": "My Config",
  "description": "Description",
  "parameters": {}
}
```

### List Configurations

```http
GET /api/langgraph/configs?tool_id=execute_comfyui_workflow
```

## Available Tools

### Workflow Execution

- **execute_n8n_workflow**: Execute n8n workflows
- **execute_comfyui_workflow**: Execute ComfyUI image generation workflows
- **execute_3dglenn_workflow**: Execute 3Dglenn 3D model generation workflows

### Search & Discovery

- **search_workflows**: Search for available workflows
- **get_workflow_details**: Get detailed information about a workflow

### Configuration Management

- **list_saved_configs**: List saved tool configurations
- **load_saved_config**: Load a saved configuration
- **save_tool_config**: Save current parameters as a configuration

## Adding Custom Tools

```python
from app.services.langgraph import get_tool_converter, get_agent

# Register a new tool
converter = get_tool_converter()
converter.register_tool(ToolDefinition(
    tool_id="my_custom_tool",
    name="My Custom Tool",
    description="Description of what this tool does",
    parameters_schema={
        "type": "object",
        "properties": {
            "param1": {"type": "string"},
        },
        "required": ["param1"],
    },
    category="custom",
    is_safe=False,
    requires_approval=True,
))

# Register a handler
agent = get_agent()
def my_handler(state, parameters):
    # Your tool logic here
    return {"success": True, "result": "Tool executed"}

agent.register_tool_handler("my_custom_tool", my_handler)
```

## Testing

```bash
# Run all tests
pytest tests/test_langgraph.py -v

# Run specific test class
pytest tests/test_langgraph.py::TestStateManagement -v

# Run with coverage
pytest tests/test_langgraph.py --cov=app/services/langgraph
```

## State Machine Flow

```
User Input
    ↓
Process Input
    ↓
Convert to Tools
    ↓
    ├─→ No tools needed → Generate Response → END
    ├─→ Safe tools → Execute Tools → Generate Response → END
    └─→ Unsafe tools → Check Approval
                          ↓
                    ├─→ Approved → Execute Tools → Generate Response → END
                    ├─→ Rejected → Generate Response → END
                    └─→ Pending → Wait for user → Resume
```

## Error Handling

The agent handles various error scenarios:

- **Invalid tool parameters**: Returns validation errors
- **Tool execution failures**: Captures and reports errors
- **Approval timeouts**: Automatically expires pending requests
- **Session not found**: Creates new session automatically
- **Redis unavailable**: Degrades gracefully (no persistence)

## Security

- **User authentication**: Required for approval actions
- **Tool ownership**: Users can only access their own configurations
- **Approval tracking**: All approvals are logged with user ID
- **Safe tool classification**: Safe tools can be auto-approved

## Performance

- **Redis caching**: Fast session state retrieval
- **Async operations**: Non-blocking tool execution
- **Connection pooling**: Efficient database and Redis connections
- **State compression**: Minimal data transfer

## Future Enhancements

- [ ] Multi-tool execution in parallel
- [ ] Tool chaining and dependencies
- [ ] Advanced approval workflows (multi-user, time-based)
- [ ] Tool usage analytics and recommendations
- [ ] Natural language parameter refinement
- [ ] Webhook notifications for approval requests
- [ ] Integration with external approval systems

## License

MIT