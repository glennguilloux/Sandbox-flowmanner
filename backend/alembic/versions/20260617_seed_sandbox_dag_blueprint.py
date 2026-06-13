"""Seed a sample sandbox DAG workflow template into blueprints.

Inserts a demo blueprint that showcases the Phase 3 sandbox node type
in a DAG workflow: generate code → execute in sandbox → summarize results.

Idempotent: uses ON CONFLICT (title, user_id) DO NOTHING
(based on a deterministic UUID so re-running is safe).

Revision ID: seed_sandbox_dag_blueprint
Revises: seed_sandboxd_tools
Create Date: 2026-06-17
"""

import json
from uuid import UUID, uuid4

from sqlalchemy import text as sa_text

from alembic import context, op

# revision identifiers, used by Alembic.
revision = "seed_sandbox_dag_blueprint"
down_revision = "seed_sandboxd_tools"
branch_labels = None
depends_on = None

# Deterministic UUID so the seed is idempotent across re-runs
BLUEPRINT_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# system user (id=1) — the seed owner
SYSTEM_USER_ID = 1

SAMPLE_DAG_DEFINITION = {
    "nodes": [
        {
            "id": "generate_code",
            "type": "llm_call",
            "title": "Generate Code",
            "description": "Use an LLM to generate a Python script based on the user's request.",
            "config": {
                "prompt": "{{input.task_description}}",
                "system_prompt": (
                    "You are an expert Python developer. Generate clean, "
                    "well-commented Python code that accomplishes the task. "
                    "Output ONLY the code, no explanations."
                ),
                "model_id": "deepseek-chat",
                "temperature": 0.3,
                "max_tokens": 4000,
            },
            "dependencies": [],
        },
        {
            "id": "execute_in_sandbox",
            "type": "sandbox",
            "title": "Execute in Sandbox",
            "description": "Run the generated code inside an isolated sandboxd Docker container.",
            "config": {
                "task_prompt": "Run the following Python script and report the output:\n\n{{generate_code.output.text}}",
                "template": "react-standard",
                "shared_workspace": False,
                "input_files": {
                    "main.py": "{{generate_code.output.text}}",
                },
                "snapshot_before": True,
            },
            "dependencies": ["generate_code"],
        },
        {
            "id": "summarize_results",
            "type": "llm_call",
            "title": "Summarize Results",
            "description": "Analyze the sandbox execution output and produce a summary.",
            "config": {
                "prompt": (
                    "The following Python script was executed in a sandboxed "
                    "Docker container.\n\n"
                    "## Code\n```python\n{{generate_code.output.text}}\n```\n\n"
                    "## Output\n```\n{{execute_in_sandbox.output.stdout}}\n```\n\n"
                    "Exit code: {{execute_in_sandbox.output.exit_code}}\n\n"
                    "Provide a concise summary of what the code did, "
                    "whether it succeeded, and any issues."
                ),
                "model_id": "deepseek-chat",
                "temperature": 0.5,
                "max_tokens": 2000,
            },
            "dependencies": ["execute_in_sandbox"],
        },
    ],
    "edges": [
        {"source": "generate_code", "target": "execute_in_sandbox"},
        {"source": "execute_in_sandbox", "target": "summarize_results"},
    ],
    "budget": {
        "max_cost_usd": "5.00",
        "max_wall_time_seconds": 600,
        "max_iterations": 50,
        "max_depth": 3,
    },
}

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "task_description": {
            "type": "string",
            "description": "Describe what the Python script should do.",
        },
    },
    "required": ["task_description"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Summary of the sandbox execution results.",
        },
        "exit_code": {
            "type": "integer",
            "description": "Exit code from the sandbox execution.",
        },
    },
}


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute(
            "INSERT INTO blueprints ("
            "id, user_id, title, description, "
            "blueprint_type, definition, input_schema, output_schema, "
            "status, version, tags, category, icon, "
            "run_count, created_at, updated_at"
            ") VALUES ("
            f"{_sql_literal(BLUEPRINT_ID)}, {SYSTEM_USER_ID}, "
            f"{_sql_literal('Sandbox Code Runner')}, "
            f"{_sql_literal('Generate Python code with an LLM, execute it in an isolated Docker sandbox, and summarize the results. Demonstrates the sandbox DAG node (Phase 3).')}, "
            "'dag', "
            f"{_sql_literal(json.dumps(SAMPLE_DAG_DEFINITION))}::jsonb, "
            f"{_sql_literal(json.dumps(INPUT_SCHEMA))}::jsonb, "
            f"{_sql_literal(json.dumps(OUTPUT_SCHEMA))}::jsonb, "
            "'published', 1, "
            f"{_sql_literal(json.dumps(['sandbox', 'code-execution', 'demo', 'dag']))}::jsonb, "
            f"{_sql_literal('code-execution-and-development')}, {_sql_literal('sandbox')}, "
            "0, now(), now()"
            ") ON CONFLICT DO NOTHING"
        )
        return

    conn = op.get_bind()
    conn.execute(
        sa_text(
            """
            INSERT INTO blueprints (
                id, user_id, title, description,
                blueprint_type, definition, input_schema, output_schema,
                status, version, tags, category, icon,
                run_count, created_at, updated_at
            ) VALUES (
                :id, :user_id, :title, :description,
                :blueprint_type, CAST(:definition AS jsonb),
                CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb),
                'published', 1,
                CAST(:tags AS jsonb), :category, :icon,
                0, now(), now()
            )
            ON CONFLICT DO NOTHING
            """
        ),
        {
            "id": BLUEPRINT_ID,
            "user_id": SYSTEM_USER_ID,
            "title": "Sandbox Code Runner",
            "description": (
                "Generate Python code with an LLM, execute it in an isolated "
                "Docker sandbox, and summarize the results. Demonstrates the "
                "sandbox DAG node (Phase 3)."
            ),
            "blueprint_type": "dag",
            "definition": json.dumps(SAMPLE_DAG_DEFINITION),
            "input_schema": json.dumps(INPUT_SCHEMA),
            "output_schema": json.dumps(OUTPUT_SCHEMA),
            "tags": json.dumps(["sandbox", "code-execution", "demo", "dag"]),
            "category": "code-execution-and-development",
            "icon": "sandbox",
        },
    )


def downgrade() -> None:
    if context.is_offline_mode():
        op.execute(f"DELETE FROM blueprints WHERE id = {_sql_literal(BLUEPRINT_ID)}")
        return

    conn = op.get_bind()
    conn.execute(
        sa_text("DELETE FROM blueprints WHERE id = :id"),
        {"id": BLUEPRINT_ID},
    )
