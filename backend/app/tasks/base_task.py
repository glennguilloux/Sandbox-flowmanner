"""DISABLED 2026-06-12 — pre-existing import errors at module top-level.

The original `base_task.py` is preserved in this directory for future revival
(see sibling modules and the Q1-B cleanup commit for the failure mode).

To revive this module, you need:
  1. A `CeleryTask` ORM model in `app/models/celery_task.py` (or extend
     `app/models/__init__.py`) with columns: task_id, task_name, status,
     args, kwargs, result, error, retry_count, created_at, started_at,
     completed_at.
  2. A matching alembic migration creating the `celery_tasks` table.
  3. A `TaskStatus` enum (PENDING/STARTED/COMPLETED/FAILED/RETRYING) —
     re-export it from `app.models`.
  4. Fix the broken `from celery_app import celery_app` inside
     `cleanup_old_tasks` and `health_check` factory functions
     (should be `from app.tasks.celery_app import celery_app`).

Until then this stub keeps the celery worker import graph clean.
"""
