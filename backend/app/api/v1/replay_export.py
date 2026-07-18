"""Replay Export API — /api/missions/{mission_id}/export-replay.

Produces a self-contained HTML report showing how the AI produced a
deliverable.  This is the "proof" layer: clients get the deliverable
AND a step-by-step replay of how it was built.

The replay report contains:
- Mission title and goal
- Step-by-step timeline from substrate events
- LLM calls: model, tokens, latency (summarized)
- Tool calls: tool name, inputs, outputs (summarized)
- Token usage and cost breakdown
- Final deliverable (output text)
- Timestamps and duration

Supports:
- HTML (default) — self-contained, shareable in any browser
- JSON — for programmatic access
"""

from __future__ import annotations

import html
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.mission_errors import MissionNotFoundError
from app.services.mission_service import require_mission_access
from app.services.substrate.event_log import get_event_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/missions", tags=["replay-export"])


async def _require_mission_access(db: AsyncSession, mission_id: UUID, user: User):
    try:
        return await require_mission_access(db, mission_id, user.id)
    except MissionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _escape(text: str | None) -> str:
    """HTML-escape text for safe embedding."""
    return html.escape(text or "")


def _truncate(text: str, max_len: int = 500) -> str:
    """Truncate text with ellipsis."""
    if not text or len(text) <= max_len:
        return text or ""
    return text[:max_len] + "..."


def _format_timestamp(ts: Any) -> str:
    """Format a timestamp for display."""
    if ts is None:
        return "—"
    if isinstance(ts, datetime):
        return ts.strftime("%H:%M:%S.%f")[:-3]
    return str(ts)


def _format_duration(start: datetime | None, end: datetime | None) -> str:
    """Format duration between two timestamps."""
    if not start or not end:
        return "—"
    delta = (end - start).total_seconds()
    if delta < 1:
        return f"{delta * 1000:.0f}ms"
    if delta < 60:
        return f"{delta:.1f}s"
    minutes = int(delta // 60)
    seconds = delta % 60
    return f"{minutes}m {seconds:.0f}s"


def _event_icon(event_type: str) -> str:
    """Return an emoji icon for an event type."""
    icons = {
        "mission.started": "🚀",
        "mission.completed": "✅",
        "mission.failed": "❌",
        "mission.paused": "⏸️",
        "mission.aborted": "🛑",
        "task.started": "▶️",
        "task.completed": "✓",
        "task.failed": "✗",
        "task.retrying": "🔄",
        "llm.call": "🤖",
        "tool.call": "🔧",
        "human_interrupt.raised": "👤",
        "substrate.budget_exhausted": "💰",
        "substrate.checkpoint": "📍",
        "sandbox.created": "📦",
        "sandbox.task_submitted": "📤",
        "sandbox.task_completed": "📥",
    }
    for key, icon in icons.items():
        if key in event_type:
            return icon
    return "•"


def _event_color(event_type: str) -> str:
    """Return a CSS color class for an event type."""
    if "completed" in event_type:
        return "#22c55e"  # green
    if "failed" in event_type:
        return "#ef4444"  # red
    if "llm.call" in event_type:
        return "#3b82f6"  # blue
    if "tool" in event_type or "sandbox" in event_type:
        return "#8b5cf6"  # purple
    if "human" in event_type or "hitl" in event_type:
        return "#f59e0b"  # amber
    if "started" in event_type:
        return "#6b7280"  # gray
    return "#9ca3af"


def _render_event_row(event: dict, seq_start_time: datetime | None) -> str:
    """Render a single event as an HTML table row."""
    etype = event.get("type", "unknown")
    payload = event.get("payload") or {}
    actor = event.get("actor", "system")
    ts = event.get("timestamp")
    seq = event.get("sequence", "?")
    icon = _event_icon(etype)
    color = _event_color(etype)

    # Build detail text based on event type
    details = ""
    if "llm.call" in etype:
        model = payload.get("model_id", "?")
        in_tok = payload.get("prompt_tokens", 0)
        out_tok = payload.get("completion_tokens", 0)
        cost = payload.get("cost_usd", 0)
        latency = payload.get("latency_ms", 0)
        details = (
            f'<span style="color:#6b7280">Model:</span> {_escape(model)} · '
            f'<span style="color:#6b7280">Tokens:</span> {in_tok}→{out_tok} · '
            f'<span style="color:#6b7280">Cost:</span> ${cost:.4f} · '
            f'<span style="color:#6b7280">Latency:</span> {latency}ms'
        )
    elif "task.completed" in etype or "task.failed" in etype:
        title = payload.get("task_title", payload.get("task_id", "?"))
        tokens = payload.get("tokens", 0)
        cost = payload.get("cost_usd", 0)
        error = payload.get("error", "")
        parts = [
            f'<span style="color:#6b7280">Task:</span> {_escape(str(title))}',
        ]
        if tokens:
            parts.append(f'<span style="color:#6b7280">Tokens:</span> {tokens}')
        if cost:
            parts.append(f'<span style="color:#6b7280">Cost:</span> ${cost:.4f}')
        if error:
            parts.append(f'<span style="color:#ef4444">Error:</span> {_escape(_truncate(str(error), 200))}')
        details = " · ".join(parts)
    elif "task.started" in etype:
        title = payload.get("task_title", payload.get("task_id", "?"))
        task_type = payload.get("task_type", "")
        attempt = payload.get("attempt", 1)
        details = (
            f'<span style="color:#6b7280">Task:</span> {_escape(str(title))} '
            f'<span style="color:#6b7280">({_escape(task_type)})</span>'
        )
        if attempt > 1:
            details += f' · <span style="color:#f59e0b">Attempt {attempt}</span>'
    elif "sandbox" in etype:
        sid = payload.get("sandbox_id", "")
        tid = payload.get("task_id", "")
        message = payload.get("message", "")
        parts = []
        if sid:
            parts.append(f'<span style="color:#6b7280">Sandbox:</span> {_escape(str(sid)[:8])}')
        if message:
            parts.append(_escape(_truncate(message, 150)))
        details = " · ".join(parts) if parts else _escape(_truncate(str(payload), 200))
    elif "budget_exhausted" in etype:
        reason = payload.get("reason", "")
        spent = payload.get("spent_usd", 0)
        details = f'<span style="color:#ef4444">{_escape(reason)}</span> · Spent: ${spent:.4f}'
    elif "human_interrupt" in etype:
        title = payload.get("title", "")
        itype = payload.get("interrupt_type", "")
        details = f'<span style="color:#6b7280">Type:</span> {_escape(itype)} · {_escape(str(title))}'
    else:
        # Generic payload rendering
        if payload:
            payload_str = str(payload)
            if len(payload_str) > 300:
                payload_str = payload_str[:300] + "..."
            details = f'<code style="font-size:0.75rem;color:#9ca3af">{_escape(payload_str)}</code>'

    ts_str = _format_timestamp(ts)

    return f"""
    <tr>
      <td style="padding:8px 12px;border-bottom:1px solid #1f2937;font-family:monospace;font-size:0.8rem;color:#9ca3af;white-space:nowrap">{seq}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #1f2937;white-space:nowrap">{ts_str}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #1f2937;text-align:center;font-size:1.1rem">{icon}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #1f2937">
        <span style="color:{color};font-weight:600;font-family:monospace;font-size:0.8rem">{_escape(etype)}</span>
        <div style="margin-top:4px;font-size:0.85rem;line-height:1.4">{details}</div>
      </td>
      <td style="padding:8px 12px;border-bottom:1px solid #1f2937;font-size:0.8rem;color:#6b7280">{_escape(actor)}</td>
    </tr>"""


def _render_html_report(
    mission: dict,
    events: list[dict],
    total_cost: float,
    total_tokens: int,
    duration_str: str,
) -> str:
    """Render the full HTML replay report."""
    title = _escape(mission.get("title", "Untitled Mission"))
    status_val = _escape(mission.get("status", "unknown"))
    mission_id = _escape(str(mission.get("id", "")))
    created = mission.get("created_at", "")

    # Count event types
    llm_calls = sum(1 for e in events if "llm.call" in (e.get("type") or ""))
    tool_calls = sum(1 for e in events if "tool" in (e.get("type") or "") and "llm" not in (e.get("type") or ""))
    task_completed = sum(1 for e in events if "task.completed" in (e.get("type") or ""))
    task_failed = sum(1 for e in events if "task.failed" in (e.get("type") or ""))

    # Build event rows
    first_ts = None
    for e in events:
        if e.get("timestamp"):
            first_ts = e["timestamp"]
            break

    event_rows = "\n".join(_render_event_row(e, first_ts) for e in events)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Replay: {title} — FlowManner</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; }}
    .container {{ max-width: 1000px; margin: 0 auto; padding: 2rem; }}
    .header {{ border-bottom: 1px solid #1e293b; padding-bottom: 1.5rem; margin-bottom: 2rem; }}
    .header h1 {{ font-size: 1.5rem; font-weight: 700; color: #f8fafc; }}
    .header .subtitle {{ color: #94a3b8; font-size: 0.9rem; margin-top: 0.5rem; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
    .stat {{ background: #1e293b; border-radius: 0.5rem; padding: 1rem; text-align: center; }}
    .stat .value {{ font-size: 1.5rem; font-weight: 700; color: #f8fafc; }}
    .stat .label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.25rem; }}
    .timeline {{ margin-top: 1.5rem; }}
    .timeline table {{ width: 100%; border-collapse: collapse; }}
    .timeline th {{ padding: 10px 12px; text-align: left; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; border-bottom: 1px solid #334155; background: #1e293b; position: sticky; top: 0; }}
    .footer {{ margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid #1e293b; text-align: center; font-size: 0.8rem; color: #475569; }}
    .footer a {{ color: #3b82f6; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🔄 Replay: {title}</h1>
      <div class="subtitle">Mission {mission_id} · Status: <strong>{status_val}</strong> · Created: {created}</div>
    </div>

    <div class="stats">
      <div class="stat">
        <div class="value">{len(events)}</div>
        <div class="label">Events</div>
      </div>
      <div class="stat">
        <div class="value">{llm_calls}</div>
        <div class="label">LLM Calls</div>
      </div>
      <div class="stat">
        <div class="value">{task_completed}/{task_completed + task_failed}</div>
        <div class="label">Tasks Done</div>
      </div>
      <div class="stat">
        <div class="value">{total_tokens:,}</div>
        <div class="label">Tokens</div>
      </div>
      <div class="stat">
        <div class="value">${total_cost:.4f}</div>
        <div class="label">Cost</div>
      </div>
      <div class="stat">
        <div class="value">{duration_str}</div>
        <div class="label">Duration</div>
      </div>
    </div>

    <div class="timeline">
      <h2 style="font-size:1.1rem;margin-bottom:1rem;color:#f8fafc">Event Timeline</h2>
      <table>
        <thead>
          <tr>
            <th style="width:50px">#</th>
            <th style="width:90px">Time</th>
            <th style="width:40px"></th>
            <th>Event</th>
            <th style="width:80px">Actor</th>
          </tr>
        </thead>
        <tbody>
          {event_rows}
        </tbody>
      </table>
    </div>

    <div class="footer">
      Generated by <a href="https://flowmanner.com">FlowManner</a> — Self-hosted AI workflow orchestration
    </div>
  </div>
</body>
</html>"""


@router.get("/{mission_id}/export-replay")
async def export_replay(
    mission_id: UUID,
    format: str = Query("html", description="Export format: 'html' or 'json'"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export a mission's replay as a shareable report.

    Returns a self-contained HTML page (default) or JSON showing
    the full event timeline, cost breakdown, and execution summary.

    This is the "proof" layer: clients get a deliverable AND a
    step-by-step replay of how the AI produced it.
    """
    mission = await _require_mission_access(db, mission_id, user)

    run_id = (mission.plan or {}).get("substrate_run_id")
    if not run_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission has no substrate run — cannot export replay",
        )

    # Fetch all events for this run
    event_log = get_event_log()
    raw_events = await event_log.get_events(db, str(run_id), limit=10_000)

    # Serialize events
    events = []
    for ev in raw_events:
        events.append(
            {
                "id": str(ev.id) if ev.id else None,
                "sequence": ev.sequence,
                "type": ev.type,
                "payload": ev.payload,
                "actor": ev.actor,
                "timestamp": ev.timestamp,
            }
        )

    # Compute summary stats
    total_tokens = 0
    total_cost = 0.0
    first_ts = None
    last_ts = None

    for ev in raw_events:
        payload = ev.payload or {}
        if "llm.call" in (ev.type or ""):
            total_tokens += int(payload.get("prompt_tokens", 0)) + int(payload.get("completion_tokens", 0))
            total_cost += float(payload.get("cost_usd", 0))
        if ev.timestamp:
            if first_ts is None:
                first_ts = ev.timestamp
            last_ts = ev.timestamp

    duration_str = _format_duration(first_ts, last_ts)

    mission_dict = {
        "id": str(mission.id),
        "title": mission.title,
        "status": mission.status,
        "created_at": mission.created_at.isoformat() if mission.created_at else None,
    }

    if format == "json":
        return {
            "mission": mission_dict,
            "events": [
                {
                    "sequence": e["sequence"],
                    "type": e["type"],
                    "payload": e["payload"],
                    "actor": e["actor"],
                    "timestamp": e["timestamp"].isoformat() if isinstance(e["timestamp"], datetime) else None,
                }
                for e in events
            ],
            "summary": {
                "total_events": len(events),
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 6),
                "duration": duration_str,
            },
        }

    # HTML format (default)
    html_content = _render_html_report(
        mission=mission_dict,
        events=events,
        total_cost=total_cost,
        total_tokens=total_tokens,
        duration_str=duration_str,
    )

    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=html_content)
