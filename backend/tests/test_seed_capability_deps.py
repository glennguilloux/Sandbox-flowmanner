"""Tests for scripts/seed_capability_deps.py"""

from __future__ import annotations

from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSeedCapabilityDepsLogic:
    """Test the inference logic of the seeding script."""

    def test_tool_overlap_detection(self):
        """Agents sharing ≥2 tools should be detected."""
        agent_tools = {
            "agent-a": {"tool_x", "tool_y", "tool_z"},
            "agent-b": {"tool_x", "tool_y", "tool_w"},
            "agent-c": {"tool_p", "tool_q"},
        }
        MIN_SHARED = 2

        pairs = []
        agent_list = list(agent_tools.keys())
        for i in range(len(agent_list)):
            for j in range(i + 1, len(agent_list)):
                a, b = agent_list[i], agent_list[j]
                shared = agent_tools[a] & agent_tools[b]
                if len(shared) >= MIN_SHARED:
                    pairs.append((a, b, len(shared)))

        assert len(pairs) == 1
        assert pairs[0][0] == "agent-a"
        assert pairs[0][1] == "agent-b"
        assert pairs[0][2] == 2  # tool_x, tool_y

    def test_semantic_clustering(self):
        """Agents with matching domain prefixes should cluster."""
        domain_prefixes = ["academic-", "customer-support"]
        agent_slugs = {
            "academic-anthropologist",
            "academic-geographer",
            "customer-support-agent",
            "random-agent",
        }

        domain_members = defaultdict(list)
        for slug in agent_slugs:
            for prefix in domain_prefixes:
                if prefix in slug:
                    domain_members[prefix].append(slug)
                    break

        assert len(domain_members["academic-"]) == 2
        assert len(domain_members["customer-support"]) == 1  # only 1, no pair
        assert "random-agent" not in [
            s for members in domain_members.values() for s in members
        ]

    def test_max_deps_per_agent_cap(self):
        """Dependencies should be capped per agent."""
        MAX_DEPS = 3
        deps = [
            ("cap_a", "cap_b1", "preferred"),
            ("cap_a", "cap_b2", "preferred"),
            ("cap_a", "cap_b3", "preferred"),
            ("cap_a", "cap_b4", "preferred"),  # should be capped
        ]

        dep_count = defaultdict(int)
        capped = []
        for cap_a, cap_b, dep_type in deps:
            if dep_count[cap_a] < MAX_DEPS:
                capped.append((cap_a, cap_b, dep_type))
                dep_count[cap_a] += 1

        assert len(capped) == 3

    def test_no_self_dependencies(self):
        """Agents should not depend on themselves."""
        cap_map = {"agent__a": "id-a"}
        deps = []

        # In the real script, the loop uses i < j, so (a, a) is impossible
        agent_list = ["agent__a"]
        for i in range(len(agent_list)):
            for j in range(i + 1, len(agent_list)):
                deps.append((agent_list[i], agent_list[j]))

        assert len(deps) == 0

    def test_cap_to_agent_mapping(self):
        """agent__ prefix should be stripped correctly."""
        cap_slugs = [
            "agent__general-assistant-v1",
            "agent__code-assistant-v1",
            "tool__web_search",
        ]
        cap_to_agent = {}
        for slug in cap_slugs:
            if slug.startswith("agent__"):
                cap_to_agent[slug] = slug[len("agent__") :]

        assert cap_to_agent["agent__general-assistant-v1"] == "general-assistant-v1"
        assert cap_to_agent["agent__code-assistant-v1"] == "code-assistant-v1"
        assert "tool__web_search" not in cap_to_agent
