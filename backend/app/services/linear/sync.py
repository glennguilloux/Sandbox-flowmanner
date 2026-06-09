"""
Linear Mission Sync Service

Posts mission results back to Linear issues:
- On mission completion: add comment with results, update issue state
- On mission failure: add comment with error details
"""

import logging

logger = logging.getLogger(__name__)


async def sync_mission_to_linear(
    mission_id: str,
    status: str,
    results: dict | None = None,
    error_message: str | None = None,
) -> bool:
    """
    Sync a completed/failed mission back to its linked Linear issue.

    Reads linear_issue_id from mission.plan["linear"].
    Posts a comment with results, and optionally updates the issue state.

    Returns True if synced successfully, False otherwise.
    """
    try:
        from sqlalchemy import select

        from app.database import AsyncSessionLocal
        from app.models.mission_models import Mission
        from app.services.linear.client import get_linear_client

        client = get_linear_client()
        if client is None:
            logger.debug("Linear client not available — skipping mission sync")
            return False

        # Load mission to get Linear linkage
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Mission).where(Mission.id == str(mission_id))
            )
            mission = result.scalars().first()
            if not mission:
                logger.warning("Mission %s not found for Linear sync", mission_id)
                return False

            # Extract Linear issue ID from plan
            plan = mission.plan or {}
            linear_data = plan.get("linear", {})
            issue_id = linear_data.get("issue_id")
            if not issue_id:
                logger.debug(
                    "Mission %s has no linked Linear issue — skipping sync", mission_id
                )
                return False

            # Fetch current issue to get team context
            issue = await client.get_issue(issue_id)
            if not issue:
                logger.warning("Linear issue %s not found", issue_id)
                return False

            # Build comment body
            mission_title = mission.title or "Untitled Mission"
            if status == "completed":
                comment_lines = [
                    f"✅ **Mission completed**: {mission_title}",
                    "",
                ]
                if results:
                    summary = results.get("summary", {})
                    total = summary.get("total_tasks", 0)
                    completed = summary.get("completed", 0)
                    failed = summary.get("failed", 0)
                    comment_lines.append(
                        f"- **Tasks**: {completed}/{total} completed"
                        + (f", {failed} failed" if failed else "")
                    )
                    comment_lines.append("")

                if mission.tokens_used:
                    comment_lines.append(f"- **Tokens used**: {mission.tokens_used:,}")
                if mission.actual_cost:
                    comment_lines.append(f"- **Cost**: ${mission.actual_cost:.4f}")

                # Add task details
                if results and results.get("tasks"):
                    comment_lines.append("")
                    comment_lines.append("### Task Results")
                    for task in results["tasks"]:
                        task_title = task.get("title", "Unknown")
                        output_preview = ""
                        if task.get("output") and task["output"].get("text"):
                            output_preview = task["output"]["text"][:200]
                        comment_lines.append(f"- **{task_title}** — {output_preview}")

                # Add Flowmanner link
                mission_url = f"https://flowmanner.com/missions/{mission_id}"
                comment_lines.append("")
                comment_lines.append(f"🔗 [View in Flowmanner]({mission_url})")

            elif status == "failed":
                comment_lines = [
                    f"❌ **Mission failed**: {mission_title}",
                    "",
                ]
                if error_message:
                    comment_lines.append(f"**Error**: {error_message}")
                comment_lines.append("")
                mission_url = f"https://flowmanner.com/missions/{mission_id}"
                comment_lines.append(f"🔗 [View in Flowmanner]({mission_url})")
            else:
                # Other statuses (paused, cancelled, etc.) — just post a status update
                comment_lines = [
                    f"🔄 **Mission {status}**: {mission_title}",
                    "",
                ]
                mission_url = f"https://flowmanner.com/missions/{mission_id}"
                comment_lines.append(f"🔗 [View in Flowmanner]({mission_url})")

            comment_body = "\n".join(comment_lines)
            await client.add_comment(issue_id, comment_body)
            logger.info(
                "Posted Linear comment on issue %s for mission %s", issue_id, mission_id
            )

            # Optionally update issue state
            try:
                if status == "completed":
                    # Try to find a "Done" or "Completed" state
                    team_id = issue.get("team", {}).get("id")
                    if team_id:
                        states = await client.get_workflow_states(team_id)
                        done_state = next(
                            (
                                s
                                for s in states
                                if s.get("type") in ("completed", "done")
                                or s.get("name", "").lower()
                                in ("done", "completed", "closed")
                            ),
                            None,
                        )
                        if done_state:
                            await client.update_issue(
                                issue_id, state_id=done_state["id"]
                            )
                            logger.info(
                                "Updated Linear issue %s to %s",
                                issue_id,
                                done_state["name"],
                            )
            except Exception as state_err:
                logger.debug("Could not update Linear issue state: %s", state_err)

            return True

    except Exception as e:
        logger.error("Failed to sync mission %s to Linear: %s", mission_id, e)
        return False
