# mypy: disable-error-code=attr-defined
"""
Seed agent templates

Revision ID: 2026_02_01_1400
Revises: 2026_02_01_1300_add_agent_registry
Create Date: 2026-02-01 14:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "2026_02_01_1400"
down_revision = "2026_02_01_1300_add_agent_registry"
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade function to seed initial agent templates.

    Creates 8 initial templates across 4 categories:
    - General: Universal Assistant (local), Cloud GPT Assistant (cloud)
    - Coding: Code Generator (local), Advanced Code Reviewer (cloud)
    - Vision: Image Analyzer (local), Vision Expert (cloud)
    - Reasoning: Logic Solver (local), Deep Reasoning Agent (cloud)
    """
    # Seed templates using the service
    seed_agent_templates(op)


def downgrade():
    """
    Downgrade function to remove seeded templates.

    Deletes the templates that were seeded in the upgrade.
    """
    # Delete seeded templates
    template_ids = [
        "general-assistant-local-v1",
        "general-assistant-cloud-v1",
        "coding-generator-local-v1",
        "coding-reviewer-cloud-v1",
        "vision-analyzer-local-v1",
        "vision-expert-cloud-v1",
        "reasoning-solver-local-v1",
        "reasoning-deep-cloud-v1",
    ]

    for template_id in template_ids:
        op.execute(
            sa.text("DELETE FROM agent_templates WHERE template_id = :template_id"),
            {"template_id": template_id},
        )


def seed_agent_templates(op):
    """
    Seed initial agent templates into the database.

    Uses raw SQL to insert templates idempotently (skips if already exists).
    """
    import json

    templates = [
        {
            "template_id": "general-assistant-local-v1",
            "name": "Universal Assistant",
            "description": "A versatile AI assistant capable of handling general tasks, conversations, and text generation. Optimized for local deployment.",
            "category": "general",
            "capabilities": [
                "text_generation",
                "conversation",
                "summarization",
                "question_answering",
                "translation",
            ],
            "default_config": {
                "model": "qwen2.5:14b",
                "temperature": 0.7,
                "max_tokens": 2048,
                "top_p": 0.9,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            },
            "provider": "local",
            "icon_url": "/icons/general-assistant.svg",
        },
        {
            "template_id": "general-assistant-cloud-v1",
            "name": "Cloud GPT Assistant",
            "description": "A powerful cloud-based AI assistant with advanced capabilities for complex tasks and high-volume processing.",
            "category": "general",
            "capabilities": [
                "text_generation",
                "conversation",
                "summarization",
                "question_answering",
                "translation",
                "sentiment_analysis",
                "classification",
            ],
            "default_config": {
                "model": "gpt-4",
                "temperature": 0.7,
                "max_tokens": 4096,
                "top_p": 0.95,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            },
            "provider": "cloud",
            "icon_url": "/icons/cloud-assistant.svg",
        },
        {
            "template_id": "coding-generator-local-v1",
            "name": "Code Generator",
            "description": "Specialized in generating code snippets, functions, and complete programs across multiple languages. Runs locally for privacy.",
            "category": "coding",
            "capabilities": ["code_generation", "code_completion", "text_generation"],
            "default_config": {
                "model": "codellama:7b",
                "temperature": 0.3,
                "max_tokens": 2048,
                "top_p": 0.95,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.0,
            },
            "provider": "local",
            "icon_url": "/icons/code-generator.svg",
        },
        {
            "template_id": "coding-reviewer-cloud-v1",
            "name": "Advanced Code Reviewer",
            "description": "Expert code reviewer with deep understanding of best practices, security, and performance optimization. Cloud-powered for advanced analysis.",
            "category": "coding",
            "capabilities": [
                "code_review",
                "code_generation",
                "problem_solving",
                "classification",
            ],
            "default_config": {
                "model": "gpt-4",
                "temperature": 0.2,
                "max_tokens": 4096,
                "top_p": 0.95,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            },
            "provider": "cloud",
            "icon_url": "/icons/code-reviewer.svg",
        },
        {
            "template_id": "vision-analyzer-local-v1",
            "name": "Image Analyzer",
            "description": "Local vision model for analyzing images, extracting text via OCR, and describing visual content. Privacy-focused image processing.",
            "category": "vision",
            "capabilities": ["image_analysis", "ocr", "object_detection"],
            "default_config": {
                "model": "llava:7b",
                "temperature": 0.4,
                "max_tokens": 1024,
                "top_p": 0.9,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            },
            "provider": "local",
            "icon_url": "/icons/image-analyzer.svg",
        },
        {
            "template_id": "vision-expert-cloud-v1",
            "name": "Vision Expert",
            "description": "Advanced cloud-based vision specialist for complex image understanding, visual QA, and detailed visual analysis tasks.",
            "category": "vision",
            "capabilities": [
                "image_analysis",
                "visual_qa",
                "object_detection",
                "ocr",
                "classification",
            ],
            "default_config": {
                "model": "gpt-4-vision-preview",
                "temperature": 0.5,
                "max_tokens": 2048,
                "top_p": 0.95,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            },
            "provider": "cloud",
            "icon_url": "/icons/vision-expert.svg",
        },
        {
            "template_id": "reasoning-solver-local-v1",
            "name": "Logic Solver",
            "description": "Local reasoning specialist for logical puzzles, mathematical problems, and step-by-step analytical tasks.",
            "category": "reasoning",
            "capabilities": [
                "logical_reasoning",
                "problem_solving",
                "math",
                "planning",
            ],
            "default_config": {
                "model": "qwen2.5:14b",
                "temperature": 0.2,
                "max_tokens": 2048,
                "top_p": 0.9,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            },
            "provider": "local",
            "icon_url": "/icons/logic-solver.svg",
        },
        {
            "template_id": "reasoning-deep-cloud-v1",
            "name": "Deep Reasoning Agent",
            "description": "Cloud-powered deep reasoning specialist for complex analytical tasks, strategic planning, and multi-step problem decomposition.",
            "category": "reasoning",
            "capabilities": [
                "logical_reasoning",
                "problem_solving",
                "decision_making",
                "planning",
                "math",
                "entity_extraction",
            ],
            "default_config": {
                "model": "o1-preview",
                "temperature": 0.3,
                "max_tokens": 4096,
                "top_p": 0.95,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            },
            "provider": "cloud",
            "icon_url": "/icons/deep-reasoning.svg",
        },
    ]

    for template in templates:
        op.execute(
            sa.text(
                """
                INSERT INTO agent_templates 
                (template_id, name, description, category, capabilities, default_config, provider, icon_url, rating_avg, rating_count, usage_count, is_active, created_at, updated_at)
                VALUES 
                (:template_id, :name, :description, :category, :capabilities::jsonb, :default_config::jsonb, :provider, :icon_url, 0.0, 0, 0, true, NOW(), NOW())
                ON CONFLICT (template_id) DO NOTHING
            """
            ),
            {
                "template_id": template["template_id"],
                "name": template["name"],
                "description": template["description"],
                "category": template["category"],
                "capabilities": json.dumps(template["capabilities"]),
                "default_config": json.dumps(template["default_config"]),
                "provider": template["provider"],
                "icon_url": template.get("icon_url"),
            },
        )
