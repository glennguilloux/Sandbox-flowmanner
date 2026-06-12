"""Unit tests for episodic memory redaction — Q2-Q3 Chunk 2.

Proves that sensitive raw content is NOT stored in retrieval_text.
Tests: API keys, file paths, LLM outputs, env var secrets, deny-list.
"""

from __future__ import annotations

import pytest

from app.services.episodic_memory_service import EpisodicMemoryService


def _service() -> EpisodicMemoryService:
    return EpisodicMemoryService()


class TestRedactAPIKeys:
    """Prove API keys are stripped from retrieval text."""

    def test_sk_prefix_key_redacted(self):
        svc = _service()
        text = "Used key sk-abc123def456ghi789 for deployment"
        result = svc.redact(text)
        assert "sk-abc123def456ghi789" not in result
        assert "[REDACTED_API_KEY]" in result

    def test_bearer_token_redacted(self):
        svc = _service()
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9_longtoken"
        result = svc.redact(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9_longtoken" not in result
        assert "[REDACTED_API_KEY]" in result

    def test_key_prefix_redacted(self):
        svc = _service()
        text = "API key-key_production_abc123xyz was rotated"
        result = svc.redact(text)
        assert "key_production_abc123xyz" not in result
        assert "[REDACTED_API_KEY]" in result


class TestRedactFilePaths:
    """Prove user-specific file paths are stripped."""

    def test_home_path_redacted(self):
        svc = _service()
        text = "Modified /home/glenn/projects/app/main.py successfully"
        result = svc.redact(text)
        assert "/home/glenn/" not in result
        assert "[REDACTED_PATH]" in result

    def test_macos_path_redacted(self):
        svc = _service()
        text = "Read /Users/john/Documents/secret-notes.txt"
        result = svc.redact(text)
        assert "/Users/john/" not in result
        assert "[REDACTED_PATH]" in result


class TestRedactLLMOutputs:
    """Prove long LLM outputs are stripped."""

    def test_long_llm_output_redacted(self):
        svc = _service()
        # Build a long LLM output (>200 chars after marker)
        long_output = "x" * 300
        text = f"LLM output: {long_output}"
        result = svc.redact(text)
        assert long_output not in result
        assert "[REDACTED_LLM_OUTPUT]" in result

    def test_short_llm_output_preserved(self):
        svc = _service()
        text = "LLM output: This is a short summary of the mission."
        result = svc.redact(text)
        # Short outputs should be preserved
        assert "short summary" in result


class TestRedactEnvSecrets:
    """Prove environment variable secrets are stripped."""

    def test_secret_env_var_redacted(self):
        svc = _service()
        text = "Loaded SECRET_KEY=my_super_secret_value_12345"
        result = svc.redact(text)
        assert "my_super_secret_value_12345" not in result
        assert "[REDACTED_SECRET]" in result

    def test_password_env_var_redacted(self):
        svc = _service()
        text = "DB_PASSWORD=hunter2_production_db_pass"
        result = svc.redact(text)
        assert "hunter2_production_db_pass" not in result
        assert "[REDACTED_SECRET]" in result

    def test_token_env_var_redacted(self):
        svc = _service()
        text = "API_TOKEN=ghp_abc123def456ghi789"
        result = svc.redact(text)
        assert "ghp_abc123def456ghi789" not in result
        assert "[REDACTED_SECRET]" in result


class TestRedactNoOp:
    """Prove redaction is safe on benign text."""

    def test_empty_string(self):
        svc = _service()
        assert svc.redact("") == ""

    def test_none_returns_empty(self):
        svc = _service()
        assert svc.redact("") == ""

    def test_benign_text_unchanged(self):
        svc = _service()
        text = "Mission abcd1234 step code_execute: success, cost small, 3 files modified"
        result = svc.redact(text)
        assert result == text

    def test_combined_redaction(self):
        """Prove multiple redaction types work together."""
        svc = _service()
        text = (
            "Mission deploy: success. "
            "Used sk-abc123def456ghi789 for auth. "
            "Modified /home/glenn/app/main.py. "
            "SECRET_KEY=prod_secret_xyz"
        )
        result = svc.redact(text)
        assert "sk-abc123def456ghi789" not in result
        assert "/home/glenn/" not in result
        assert "prod_secret_xyz" not in result
        # The benign parts should still be there
        assert "Mission deploy: success" in result
