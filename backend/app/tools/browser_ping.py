from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool


class BrowserPingInput(ToolInput):
    message: str = Field(default="hello", description="Message to send")


class BrowserPingTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="browser_ping",
            name="Ping Browser",
            description="Ping the browser service to verify it's working",
            category="browser",
            input_schema=BrowserPingInput.schema_extra(),
            tags=["browser", "smoke-test"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = BrowserPingInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        context = input_data.get("context")
        user_id = context.get("user_id", "anonymous") if context else "anonymous"
        response_message = f"pong: {validated.message}"

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "success": True,
                "message": response_message,
                "context_user": user_id,
            },
            metadata={"tool": self.name, "input_message": validated.message},
        )


register_tool(BrowserPingTool())
