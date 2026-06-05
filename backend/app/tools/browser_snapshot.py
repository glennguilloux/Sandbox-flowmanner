from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool


class BrowserSnapshotInput(ToolInput):
    pass


class BrowserSnapshotTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="browser_snapshot",
            name="DOM Snapshot",
            description="Get DOM snapshot with interactive element references",
            category="browser",
            input_schema=BrowserSnapshotInput.schema_extra(),
            tags=["browser"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        from app.services.browser_service import get_browser_service

        try:
            validated = BrowserSnapshotInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        context = input_data.get("context")
        if not context:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="No context provided"
            )

        user_id = context.get("user_id")
        if not user_id:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="No user_id in context"
            )

        service = get_browser_service()
        result = await service.snapshot(user_id)

        if result.get("success"):
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        else:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=result.get("error")
            )


register_tool(BrowserSnapshotTool())
