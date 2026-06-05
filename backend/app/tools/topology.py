from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool


class TopologyInput(ToolInput):
    mission_id: str | None = Field(None, description="Mission ID to visualize")
    workflow_id: str | None = Field(None, description="Workflow ID to visualize")


class TopologyTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="topology_graph",
            name="Topology Graph",
            description="Generate graph data (nodes + edges) for a mission or workflow",
            category="topology",
            input_schema=TopologyInput.schema_extra(),
            tags=["graph", "visualization", "mission", "workflow"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TopologyInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal as get_db_session
            from app.models.graph import GraphWorkflow
            from app.models.mission_models import Mission

            mission_id = validated.mission_id
            workflow_id = validated.workflow_id

            if workflow_id:
                async with get_db_session() as session:
                    result = await session.execute(
                        select(GraphWorkflow).where(GraphWorkflow.id == workflow_id)
                    )
                    workflow = result.scalar_one_or_none()
                    if not workflow:
                        return ToolResult.error_result(
                            tool_id=self.tool_id,
                            error=f"Workflow not found: {workflow_id}",
                        )

                    graph_def = workflow.graph_definition or {}
                    nodes = graph_def.get("nodes", [])
                    edges = graph_def.get("edges", [])

                    return ToolResult.success_result(
                        tool_id=self.tool_id,
                        result={"nodes": nodes, "edges": edges, "name": workflow.name},
                    )

            if mission_id:
                async with get_db_session() as session:
                    result = await session.execute(
                        select(Mission).where(Mission.id == mission_id)
                    )
                    mission = result.scalar_one_or_none()
                    if not mission:
                        return ToolResult.error_result(
                            tool_id=self.tool_id,
                            error=f"Mission not found: {mission_id}",
                        )

                    nodes = []
                    edges = []
                    if (
                        hasattr(mission, "graph_definition")
                        and mission.graph_definition
                    ):
                        nodes = mission.graph_definition.get("nodes", [])
                        edges = mission.graph_definition.get("edges", [])

                    return ToolResult.success_result(
                        tool_id=self.tool_id,
                        result={
                            "nodes": nodes,
                            "edges": edges,
                            "name": getattr(mission, "title", mission_id),
                        },
                    )

            async with get_db_session() as session:
                wf_result = await session.execute(select(GraphWorkflow).limit(50))
                workflows = wf_result.scalars().all()

                m_result = await session.execute(select(Mission).limit(50))
                missions = m_result.scalars().all()

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "workflows": [
                        {"id": str(w.id), "name": w.name, "status": w.status}
                        for w in workflows
                    ],
                    "missions": [{"id": str(m.id), "name": m.name} for m in missions],
                },
            )

        except ImportError as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Database models not available: {e}",
            )
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(TopologyTool())
