"""Plugin Loader — loads .fmp packages and registers handlers.

Handles unpacking, manifest validation, entry point import,
and dynamic handler registration into the NodeHandlerRegistry.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from app.sdk.exceptions import ManifestError, PluginLoadError
from app.sdk.manifest import PluginManifest

logger = logging.getLogger(__name__)


def load_manifest_from_fmp(fmp_path: Path) -> PluginManifest:
    """Extract and validate the manifest from a .fmp archive.

    Args:
        fmp_path: Path to the .fmp file.

    Returns:
        Validated PluginManifest.

    Raises:
        ManifestError: If manifest is missing or invalid.
        FileNotFoundError: If the .fmp file doesn't exist.
    """
    if not fmp_path.exists():
        raise FileNotFoundError(f"Plugin package not found: {fmp_path}")

    with zipfile.ZipFile(fmp_path, "r") as zf:
        manifest_names = [
            n
            for n in zf.namelist()
            if n.endswith("flowmanner-plugin.yaml") and "/" not in n.replace("\\", "/").lstrip("/")
        ]
        if not manifest_names:
            raise ManifestError("No flowmanner-plugin.yaml found in .fmp package")

        raw = zf.read(manifest_names[0]).decode("utf-8")

    import yaml

    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a YAML mapping")

    return PluginManifest(**data)


def unpack_fmp(fmp_path: Path, target_dir: Path | None = None) -> Path:
    """Unpack a .fmp archive to a directory.

    Args:
        fmp_path: Path to the .fmp file.
        target_dir: Target directory. Defaults to a temp directory.

    Returns:
        Path to the unpacked plugin directory.
    """
    if target_dir is None:
        target_dir = Path(tempfile.mkdtemp(prefix="fm_plugin_"))
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(fmp_path, "r") as zf:
        zf.extractall(target_dir)

    return target_dir


def import_plugin_entry(
    plugin_dir: Path,
    manifest: PluginManifest,
) -> Any:
    """Import the plugin entry point module and find the BasePlugin subclass.

    Args:
        plugin_dir: Unpacked plugin directory.
        manifest: Validated manifest.

    Returns:
        An instance of the plugin's BasePlugin subclass.

    Raises:
        PluginLoadError: If import fails or no BasePlugin found.
    """
    entry = manifest.entry_point
    module_path = plugin_dir / f"{entry}.py"
    package_path = plugin_dir / entry / "__init__.py"

    target: Path
    module_name: str

    if module_path.exists():
        target = module_path
        module_name = f"_plugin_{manifest.name}_{entry}"
    elif package_path.exists():
        target = package_path
        module_name = f"_plugin_{manifest.name}_{entry}"
    else:
        raise PluginLoadError(
            f"Entry point module not found: {entry}.py or {entry}/__init__.py",
            plugin_name=manifest.name,
        )

    # Add plugin dir to sys.path so relative imports work
    plugin_dir_str = str(plugin_dir)
    path_added = False
    if plugin_dir_str not in sys.path:
        sys.path.insert(0, plugin_dir_str)
        path_added = True

    try:
        spec = importlib.util.spec_from_file_location(module_name, str(target))
        if spec is None or spec.loader is None:
            raise PluginLoadError(
                f"Cannot create module spec for {target}",
                plugin_name=manifest.name,
            )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except PluginLoadError:
        raise
    except Exception as e:
        raise PluginLoadError(
            f"Failed to import entry point: {e}",
            plugin_name=manifest.name,
        ) from e
    finally:
        if path_added and plugin_dir_str in sys.path:
            sys.path.remove(plugin_dir_str)

    # Find BasePlugin subclass
    from app.sdk.base import BasePlugin

    plugin_instance = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
            plugin_instance = attr()
            break

    if plugin_instance is None:
        raise PluginLoadError(
            "Entry point module does not define a BasePlugin subclass",
            plugin_name=manifest.name,
        )

    # Validate that declared node types match handler IDs
    manifest_ids = {nt.id for nt in manifest.node_types}
    handler_ids = set(plugin_instance.node_type_ids())
    if manifest_ids != handler_ids:
        missing = manifest_ids - handler_ids
        extra = handler_ids - manifest_ids
        parts = []
        if missing:
            parts.append(f"declared but not implemented: {missing}")
        if extra:
            parts.append(f"implemented but not declared: {extra}")
        raise PluginLoadError(
            f"Node type mismatch: {'; '.join(parts)}",
            plugin_name=manifest.name,
        )

    return plugin_instance


def load_plugin_from_dir(plugin_dir: Path) -> tuple[PluginManifest, Any]:
    """Load a plugin from an unpacked directory.

    Returns:
        (manifest, plugin_instance) tuple.
    """
    manifest_path = plugin_dir / "flowmanner-plugin.yaml"
    if not manifest_path.exists():
        raise ManifestError(f"Manifest not found: {manifest_path}")

    import yaml

    with open(manifest_path) as f:
        raw = yaml.safe_load(f)

    manifest = PluginManifest(**raw)
    plugin_instance = import_plugin_entry(plugin_dir, manifest)

    logger.info(
        "Loaded plugin '%s' v%s with %d handler(s)",
        manifest.name,
        manifest.version,
        len(plugin_instance.handlers),
    )
    return manifest, plugin_instance


def load_plugin_from_fmp(fmp_path: Path) -> tuple[PluginManifest, Any, Path]:
    """Load a plugin from a .fmp archive file.

    Returns:
        (manifest, plugin_instance, unpack_dir) tuple.
    """
    manifest = load_manifest_from_fmp(fmp_path)
    unpack_dir = unpack_fmp(fmp_path)
    _, plugin_instance = load_plugin_from_dir(unpack_dir)
    return manifest, plugin_instance, unpack_dir
