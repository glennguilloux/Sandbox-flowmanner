#!/usr/bin/env python3
"""
OpenWhisk Action Manager

Manages OpenWhisk action deployment, lifecycle, and metadata.
Handles versioning, dependencies, and action packaging.
"""

import io
import json
import logging
import os
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .client import OpenWhiskClient

logger = logging.getLogger(__name__)


@dataclass
class ActionPackage:
    """OpenWhisk action package"""

    name: str
    version: str
    code: str
    main: str = 'main'
    dependencies: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=dict)
    description: str = ''
    runtime: str = 'python:3.11'


@dataclass
class ActionMetadata:
    """Action metadata"""

    name: str
    version: str
    created_at: datetime
    updated_at: datetime
    author: str = ''
    tags: list[str] = field(default_factory=list)
    category: str = 'general'


class OpenWhiskActionManager:
    """
    Manager for OpenWhisk actions

    Responsibilities:
    - Package actions for deployment
    - Manage action dependencies
    - Handle action versioning
    - Generate action manifests
    """

    def __init__(self, client: OpenWhiskClient):
        """
        Initialize action manager

        Args:
            client: OpenWhisk client instance
        """
        self.client = client
        self.action_manifests: dict[str, ActionMetadata] = {}

        logger.info("OpenWhiskActionManager initialized")

    async def package_action(
        self,
        action_package: ActionPackage
    ) -> dict[str, Any]:
        """
        Package an action for deployment

        Args:
            action_package: ActionPackage with code and metadata

        Returns:
            Package information with base64 encoded zip or direct code

        Example:
            >>> pkg = ActionPackage(
            ...     name='test_action',
            ...     code='def main(args): ...',
            ...     runtime='python:3.11'
            ... )
            >>> packaged = await manager.package_action(pkg)
        """
        logger.info(f"Packaging action: {action_package.name}")

        # If no dependencies, return code directly
        if not action_package.dependencies and not action_package.requirements:
            return {
                'name': action_package.name,
                'version': action_package.version,
                'code': action_package.code,
                'runtime': action_package.runtime,
                'main': action_package.main,
                'packaging_type': 'direct'
            }

        # Otherwise, create zip package
        try:
            zip_buffer = io.BytesIO()

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add main code
                zf.writestr(f"{action_package.name}.py", action_package.code)

                # Add requirements.txt if needed
                if action_package.requirements:
                    requirements = '\n'.join(action_package.requirements)
                    zf.writestr('requirements.txt', requirements)

                # Add dependency files
                for dep_file in action_package.dependencies:
                    if os.path.exists(dep_file):
                        zf.write(dep_file, os.path.basename(dep_file))

            zip_buffer.seek(0)
            zip_data = zip_buffer.read()

            return {
                'name': action_package.name,
                'version': action_package.version,
                'code': zip_data,
                'runtime': action_package.runtime,
                'main': action_package.main,
                'packaging_type': 'zip',
                'zip_size_bytes': len(zip_data)
            }

        except Exception as e:
            logger.error(f"Error packaging action {action_package.name}: {e}")
            raise

    async def deploy_package(
        self,
        action_package: ActionPackage,
        overwrite: bool = True
    ) -> dict[str, Any]:
        """
        Deploy an action package to OpenWhisk

        Args:
            action_package: ActionPackage to deploy
            overwrite: Overwrite existing action

        Returns:
            Deployment result

        Example:
            >>> result = await manager.deploy_package(action_package)
            >>> print(result['activation_url'])
        """
        logger.info(f"Deploying package: {action_package.name} v{action_package.version}")

        try:
            # Package the action
            packaged = await self.package_action(action_package)

            # Determine deployment parameters
            params = {
                'action_name': action_package.name,
                'code': packaged['code'],
                'kind': action_package.runtime,
                'main': action_package.main,
                'description': action_package.description
            }

            # Add parameters if defined
            if action_package.parameters:
                params['parameters'] = action_package.parameters

            # Add limits if defined
            if action_package.limits:
                params['limits'] = action_package.limits

            # Deploy to OpenWhisk
            result = await self.client.create_action(**params)

            # Store metadata
            metadata = ActionMetadata(
                name=action_package.name,
                version=action_package.version,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                tags=action_package.tags
            )

            self.action_manifests[action_package.name] = metadata

            logger.info(f"Package deployed successfully: {action_package.name}")
            return {
                'success': True,
                'action_name': action_package.name,
                'version': action_package.version,
                'packaging_type': packaged['packaging_type'],
                'metadata': {
                    'created_at': metadata.created_at.isoformat(),
                    'updated_at': metadata.updated_at.isoformat()
                }
            }

        except Exception as e:
            logger.error(f"Failed to deploy package {action_package.name}: {e}")
            return {
                'success': False,
                'action_name': action_package.name,
                'error': str(e)
            }

    async def deploy_from_directory(
        self,
        actions_dir: str,
        pattern: str = '*.py'
    ) -> dict[str, Any]:
        """
        Deploy all actions from a directory

        Args:
            actions_dir: Directory containing action files
            pattern: File pattern to match (default: *.py)

        Returns:
            Deployment summary

        Example:
            >>> result = await manager.deploy_from_directory('/path/to/actions')
            >>> print(f"Deployed {result['deployed_count']} actions")
        """
        logger.info(f"Deploying actions from {actions_dir}")

        if not os.path.exists(actions_dir):
            return {
                'success': False,
                'error': f"Directory not found: {actions_dir}",
                'deployed_count': 0,
                'failed_count': 0
            }

        deployed = []
        failed = []

        for filename in os.listdir(actions_dir):
            if not filename.endswith('.py') or filename.startswith('_'):
                continue

            action_name = filename.replace('.py', '')
            filepath = os.path.join(actions_dir, filename)

            try:
                with open(filepath, 'r') as f:
                    code = f.read()

                package = ActionPackage(
                    name=action_name,
                    version='1.0.0',
                    code=code,
                    runtime='python:3.11',
                    description=f'Auto-deployed: {action_name}'
                )

                result = await self.deploy_package(package)

                if result.get('success'):
                    deployed.append(action_name)
                else:
                    failed.append(action_name)

            except Exception as e:
                failed.append(action_name)
                logger.error(f"Failed to read/deploy {filename}: {e}")

        summary = {
            'success': len(failed) == 0,
            'deployed_count': len(deployed),
            'failed_count': len(failed),
            'deployed_actions': deployed,
            'failed_actions': failed,
            'timestamp': datetime.now(UTC).isoformat()
        }

        logger.info(
            f"Directory deployment complete: {len(deployed)} succeeded, "
            f"{len(failed)} failed"
        )

        return summary

    def create_manifest(self, action_name: str, **metadata) -> str:
        """
        Create action manifest file

        Args:
            action_name: Name of action
            **metadata: Additional metadata fields

        Returns:
            JSON manifest string
        """
        manifest = {
            'name': action_name,
            'version': metadata.get('version', '1.0.0'),
            'runtime': metadata.get('runtime', 'python:3.11'),
            'description': metadata.get('description', ''),
            'author': metadata.get('author', 'Workflows Platform'),
            'created': metadata.get('created', datetime.now(UTC).isoformat()),
            'tags': metadata.get('tags', []),
            'category': metadata.get('category', 'general')
        }

        return json.dumps(manifest, indent=2)

    def load_manifest(self, manifest_path: str) -> ActionMetadata | None:
        """
        Load action manifest from file

        Args:
            manifest_path: Path to manifest.json file

        Returns:
            ActionMetadata or None if not found
        """
        if not os.path.exists(manifest_path):
            logger.warning(f"Manifest not found: {manifest_path}")
            return None

        try:
            with open(manifest_path, 'r') as f:
                data = json.load(f)

            metadata = ActionMetadata(
                name=data['name'],
                version=data['version'],
                created_at=datetime.fromisoformat(data.get('created')),
                updated_at=datetime.fromisoformat(data.get('updated')),
                author=data.get('author', ''),
                tags=data.get('tags', []),
                category=data.get('category', 'general')
            )

            self.action_manifests[data['name']] = metadata
            return metadata

        except Exception as e:
            logger.error(f"Error loading manifest {manifest_path}: {e}")
            return None

    def get_all_manifests(self) -> dict[str, ActionMetadata]:
        """
        Get all action manifests

        Returns:
            Dictionary of action manifests by name
        """
        return self.action_manifests

    def validate_action_name(self, name: str) -> tuple[bool, str | None]:
        """
        Validate action name according to OpenWhisk naming rules

        Args:
            name: Action name to validate

        Returns:
            (is_valid, error_message)
        """
        if not name or len(name) < 1:
            return False, "Action name cannot be empty"

        if len(name) > 256:
            return False, "Action name too long (max 256 characters)"

        # Allowed characters: alphanumeric, underscore, dash
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return False, "Action name can only contain alphanumeric, underscore, and dash"

        return True, None


def create_action_manager(
    client: OpenWhiskClient | None = None
) -> OpenWhiskActionManager | None:
    """
    Factory function to create action manager

    Args:
        client: OpenWhisk client or None (auto-create)

    Returns:
        OpenWhiskActionManager instance or None if not configured

    Example:
        >>> manager = create_action_manager()
        >>> if manager:
        >>>     pkg = ActionPackage(name='test', code='...')
        >>>     await manager.deploy_package(pkg)
    """
    try:
        if client is None:
            from .client import get_openwhisk_client
            client = get_openwhisk_client()

        if not client:
            logger.warning("Cannot create action manager: client not configured")
            return None

        manager = OpenWhiskActionManager(client=client)
        logger.info("Action manager created successfully")
        return manager

    except Exception as e:
        logger.error(f"Error creating action manager: {e}")
        return None
