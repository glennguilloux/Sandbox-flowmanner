from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool


class BrowserNavigateInput(ToolInput):
    url: str = Field(..., description="URL to navigate to")


class BrowserNavigateTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            visibility="default_on",
            tool_id="browser_navigate",
            name="Navigate Browser",
            description="Navigate a browser to a URL and get the page title and status",
            category="browser",
            input_schema=BrowserNavigateInput.schema_extra(),
            tags=["browser"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        from app.services.browser_service import get_browser_service

        try:
            validated = BrowserNavigateInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        context = input_data.get("context")
        if not context:
            return ToolResult.error_result(tool_id=self.tool_id, error="No context provided")

        user_id = context.get("user_id")
        if not user_id:
            return ToolResult.error_result(tool_id=self.tool_id, error="No user_id in context")

        service = get_browser_service()
        result = await service.navigate(user_id, validated.url)

        if result.get("success"):
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        else:
            return ToolResult.error_result(tool_id=self.tool_id, error=result.get("error"))


register_tool(BrowserNavigateTool())
