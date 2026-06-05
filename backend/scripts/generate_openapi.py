#!/usr/bin/env python3
"""Generate OpenAPI specification from FastAPI application.

Usage:
    python generate_openapi.py [--output openapi.json]
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main_fastapi import app


def generate_openapi(output_path: str = "openapi.json"):
    """Generate OpenAPI spec and save to file."""
    # Get OpenAPI schema
    openapi_schema = app.openapi()

    # Add versioning info to schema
    openapi_schema["info"]["x-api-versions"] = {
        "supported": ["v1"],
        "deprecated": [],
        "current": "v1",
    }

    # Add version negotiation documentation
    openapi_schema["info"]["x-version-negotiation"] = {
        "methods": [
            "Accept-Version header",
            "URL path prefix (/api/v1/...)",
            "Query parameter (?version=v1)",
        ],
        "default": "v1",
    }

    # Write to file
    with open(output_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)

    print(f"OpenAPI spec generated: {output_path}")
    print(f"Endpoints: {len(openapi_schema.get('paths', {}))}")
    return openapi_schema


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate OpenAPI specification")
    parser.add_argument(
        "--output",
        default="openapi.json",
        help="Output file path (default: openapi.json)",
    )
    args = parser.parse_args()
    generate_openapi(args.output)
