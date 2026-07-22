from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool


class BrowserScrollInput(ToolInput):
    x: int = Field(default=0, description="Horizontal scroll pixels")
    y: int = Field(default=300, description="Vertical scroll pixels")


class BrowserScrollTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="browser_scroll",
            name="Scroll Browser",
            description="Scroll the page by x, y pixels",
            category="browser",
            input_schema=BrowserScrollInput.schema_extra(),
            tags=["browser"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        from app.services.browser_service import get_browser_service

        context = input_data.pop("context", None)

        try:
            validated = BrowserScrollInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if not context:
            return ToolResult.error_result(tool_id=self.tool_id, error="No context provided")

        user_id = context.get("user_id")
        if not user_id:
            return ToolResult.error_result(tool_id=self.tool_id, error="No user_id in context")

        service = get_browser_service()
        result = await service.scroll(user_id, validated.x, validated.y)

        if result.get("success"):
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        else:
            return ToolResult.error_result(tool_id=self.tool_id, error=result.get("error"))


register_tool(BrowserScrollTool())
