"""Tool bindings for Claude with function calling support"""

from langchain_core.tools import tool


@tool
def execute_n8n_workflow_tool(workflow_name: str, parameters: dict = None) -> str:
    """Execute an n8n workflow by name with optional parameters."""
    try:
        # Import here to avoid circular dependencies
        from app.routes.ai_routes import execute_n8n_workflow

        result = execute_n8n_workflow(workflow_name, parameters or {})
        return f"Workflow '{workflow_name}' executed successfully: {result}"
    except Exception as e:
        return f"Error executing workflow: {e!s}"


@tool
def generate_image_tool(prompt: str, style: str = "default") -> str:
    """Generate an image using ComfyUI with the given prompt."""
    try:
        from app.routes.comfyui_routes import generate_image

        result = generate_image(prompt, style)
        return f"Image generated successfully: {result}"
    except Exception as e:
        return f"Error generating image: {e!s}"


@tool
def execute_sandbox_tool(code: str, language: str = "python") -> str:
    """Execute code in sandbox environment."""
    try:
        from app.routes.sandbox_routes import execute_sandbox_code

        result = execute_sandbox_code(code, language)
        return f"Code execution result: {result}"
    except Exception as e:
        return f"Error executing code: {e!s}"


@tool
def generate_tts_tool(text: str, voice: str = "default") -> str:
    """Generate text-to-speech audio."""
    try:
        from app.routes.tts_routes import generate_tts

        result = generate_tts(text, voice)
        return f"TTS generated successfully: {result}"
    except Exception as e:
        return f"Error generating TTS: {e!s}"


# List of all tools for binding
CLAUDE_TOOLS = [
    execute_n8n_workflow_tool,
    generate_image_tool,
    execute_sandbox_tool,
    generate_tts_tool,
]
