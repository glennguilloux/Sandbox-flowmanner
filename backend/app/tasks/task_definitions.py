"""DISABLED 2026-06-12 — missing models and service.

The original `task_definitions.py` is preserved in `_disabled/` for revival.

To revive this module, you need:
  1. A `WorkflowRuns` ORM model (table `workflow_runs` with `run_id`,
     `status`, `started_at` columns used by `sync_workflow_status`).
     The closest existing model is `app.models.graph.GraphExecution`
     (consolidated from GraphWorkflow + Flow during H4.2) — likely
     re-point this task to that model and rewrite the stuck-workflow
     query accordingly.
  2. A `MonitoringService` class in `app/services/monitoring_service.py`
     exposing `update_workflow_metrics()`, `update_system_health()`,
     `update_resource_usage()`.

Until then this stub keeps the celery worker import graph clean.
"""
