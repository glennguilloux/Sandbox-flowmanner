#!/usr/bin/env python3
"""
Agent Personality Loader
Loads agent personality prompts from markdown files.
"""

import json
from pathlib import Path
from typing import Any

import yaml


class AgentPersonalityLoader:
    """Load agent personalities from markdown files."""
    
    def __init__(self, base_dir: str = "/workspace/apps/backend/agent_personalities"):
        self.base_dir = Path(base_dir)
        self.index_path = self.base_dir / "index.json"
    
    def load_all(self) -> list[dict[str, Any]]:
        """Load all agent personalities from markdown files."""
        agents = []
        
        for domain_path in self.base_dir.iterdir():
            if not domain_path.is_dir():
                continue
            
            domain = domain_path.name
            
            for md_file in domain_path.glob("*.md"):
                agent = self._load_agent(md_file, domain)
                if agent:
                    agents.append(agent)
        
        return agents
    
    def _load_agent(self, filepath: Path, domain: str) -> dict[str, Any]:
        """Load a single agent from a markdown file."""
        try:
            with open(filepath, 'r') as f:
                content = f.read()
            
            if not content.startswith('---'):
                return None
            
            parts = content.split('---', 2)
            if len(parts) < 3:
                return None
            
            frontmatter = yaml.safe_load(parts[1])
            body = parts[2].strip()
            
            sections = self._parse_sections(body)
            
            return {
                "id": f"{domain}/{filepath.stem}",
                "domain": domain,
                "name": frontmatter.get('name', filepath.stem),
                "description": frontmatter.get('description', ''),
                "color": frontmatter.get('color', 'gray'),
                "identity": sections.get('identity', ''),
                "mission": sections.get('mission', ''),
                "rules": sections.get('rules', []),
                "capabilities": sections.get('capabilities', []),
                "system_prompt": self._build_system_prompt(frontmatter, sections),
                "source_file": str(filepath)
            }
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return None
    
    def _parse_sections(self, body: str) -> dict[str, Any]:
        """Parse markdown sections into structured data."""
        sections = {}
        current_section = None
        current_content = []
        
        for line in body.split('\n'):
            if line.startswith('## '):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line[3:].lower().replace(' ', '_')
                current_content = []
            else:
                current_content.append(line)
        
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
        
        for key in ['rules', 'capabilities']:
            if key in sections:
                items = []
                for line in sections[key].split('\n'):
                    line = line.strip()
                    if line.startswith('- '):
                        items.append(line[2:])
                sections[key] = items
        
        return sections
    
    def _build_system_prompt(self, frontmatter: dict, sections: dict) -> str:
        """Build a complete system prompt from the agent data."""
        parts = []
        
        if 'identity' in sections:
            parts.append(f"# Identity\n\n{sections['identity']}")
        
        if 'mission' in sections:
            parts.append(f"# Mission\n\n{sections['mission']}")
        
        if sections.get('rules'):
            parts.append("# Rules\n")
            for rule in sections['rules']:
                parts.append(f"- {rule}")
        
        if sections.get('capabilities'):
            parts.append("\n# Capabilities\n")
            for cap in sections['capabilities']:
                parts.append(f"- {cap}")
        
        return '\n'.join(parts)
    
    def get_index(self) -> dict[str, Any]:
        """Load or generate the index file."""
        if self.index_path.exists():
            with open(self.index_path, 'r') as f:
                return json.load(f)
        return {"domains": {}, "agents": []}
    
    def get_by_domain(self, domain: str) -> list[dict[str, Any]]:
        """Get all agents for a specific domain."""
        agents = self.load_all()
        return [a for a in agents if a['domain'] == domain]
    
    def get_by_id(self, agent_id: str) -> dict[str, Any]:
        """Get a specific agent by ID."""
        agents = self.load_all()
        for agent in agents:
            if agent['id'] == agent_id:
                return agent
        return None


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Load agent personalities")
    parser.add_argument("--domain", "-d", help="Filter by domain")
    parser.add_argument("--id", "-i", help="Get specific agent by ID")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    loader = AgentPersonalityLoader()
    
    if args.id:
        agent = loader.get_by_id(args.id)
        if agent:
            print(json.dumps(agent, indent=2) if args.json else agent['system_prompt'])
        else:
            print(f"Agent not found: {args.id}")
    elif args.domain:
        agents = loader.get_by_domain(args.domain)
        print(json.dumps(agents, indent=2) if args.json else f"Found {len(agents)} agents in {args.domain}")
    else:
        agents = loader.load_all()
        if args.json:
            print(json.dumps(agents, indent=2))
        else:
            print(f"Loaded {len(agents)} agents across {len({a['domain'] for a in agents})} domains")
            for agent in agents:
                print(f"  - {agent['name']} ({agent['domain']})")
