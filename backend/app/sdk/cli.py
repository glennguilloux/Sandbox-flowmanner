"""Plugin SDK CLI commands — validate, pack, dev.

These are utility functions that can be invoked from a CLI entry point
or programmatically for plugin development workflows.

Usage::

    python -m app.sdk.cli validate ./my-plugin/
    python -m app.sdk.cli pack ./my-plugin/ -o my-plugin.fmp
    python -m app.sdk.cli dev ./my-plugin/ --port 8001
"""

from __future__ import annotations

import logging
import sys
import tempfile
import zipfile
from pathlib import Path

import yaml

from app.sdk.exceptions import ManifestError, PluginLoadError
from app.sdk.manifest import PluginManifest

logger = logging.getLogger(__name__)


def validate_manifest(manifest_path: Path) -> PluginManifest:
    """Parse and validate a plugin manifest file.

    Args:
        manifest_path: Path to flowmanner-plugin.yaml.

    Returns:
        Validated PluginManifest instance.

    Raises:
        ManifestError: If the manifest is invalid or missing.
    """
    if not manifest_path.exists():
        raise ManifestError(f"Manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ManifestError("Manifest must be a YAML mapping")

    try:
        return PluginManifest(**raw)
    except Exception as e:
        raise ManifestError(f"Invalid manifest: {e}") from e


def validate_entry_point(plugin_dir: Path, manifest: PluginManifest) -> None:
    """Check that the entry point module exists and has a BasePlugin subclass.

    Args:
        plugin_dir: Root directory of the plugin.
        manifest: Validated manifest.

    Raises:
        PluginLoadError: If entry point is missing or invalid.
    """
    entry = manifest.entry_point
    module_path = plugin_dir / f"{entry}.py"
    package_path = plugin_dir / entry / "__init__.py"

    if not module_path.exists() and not package_path.exists():
        raise PluginLoadError(
            f"Entry point module not found: {entry}.py or {entry}/__init__.py",
            plugin_name=manifest.name,
        )

    # Basic AST check — look for BasePlugin subclass
    import ast

    target = module_path if module_path.exists() else package_path
    try:
        tree = ast.parse(target.read_text(), filename=str(target))
    except SyntaxError as e:
        raise PluginLoadError(
            f"Syntax error in entry point: {e}",
            plugin_name=manifest.name,
        ) from e

    has_plugin_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = ""
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name == "BasePlugin":
                    has_plugin_class = True
                    break

    if not has_plugin_class:
        raise PluginLoadError(
            "Entry point must define a class that inherits from BasePlugin",
            plugin_name=manifest.name,
        )


def validate_plugin(plugin_dir: str | Path) -> PluginManifest:
    """Full validation: manifest + entry point + node type consistency.

    Args:
        plugin_dir: Root directory of the plugin.

    Returns:
        Validated PluginManifest.

    Raises:
        ManifestError: If manifest is invalid.
        PluginLoadError: If entry point is invalid.
    """
    plugin_dir = Path(plugin_dir)
    manifest_path = plugin_dir / "flowmanner-plugin.yaml"

    manifest = validate_manifest(manifest_path)
    validate_entry_point(plugin_dir, manifest)

    logger.info(
        "Plugin '%s' v%s validated — %d node type(s), permissions: %s",
        manifest.name,
        manifest.version,
        len(manifest.node_types),
        manifest.permissions or ["none"],
    )
    return manifest


def pack_plugin(plugin_dir: str | Path, output: str | Path | None = None) -> Path:
    """Pack a plugin directory into a .fmp archive.

    .fmp files are ZIP archives containing:
    - flowmanner-plugin.yaml (manifest)
    - Python source files
    - Any additional assets

    Args:
        plugin_dir: Root directory of the plugin.
        output: Output path. Defaults to <name>-<version>.fmp in cwd.

    Returns:
        Path to the created .fmp file.

    Raises:
        ManifestError: If manifest validation fails.
    """
    plugin_dir = Path(plugin_dir)
    manifest = validate_plugin(plugin_dir)

    if output is None:
        output = Path(f"{manifest.name}-{manifest.version}.fmp")
    output = Path(output)

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(plugin_dir.rglob("*")):
            if file_path.is_dir():
                continue
            # Skip hidden files, __pycache__, .pyc
            rel = file_path.relative_to(plugin_dir)
            parts = rel.parts
            if any(p.startswith(".") or p == "__pycache__" for p in parts):
                continue
            if file_path.suffix == ".pyc":
                continue
            zf.write(file_path, str(rel))

    logger.info("Packed plugin '%s' v%s → %s", manifest.name, manifest.version, output)
    return output


def unpack_plugin(fmp_path: str | Path, target_dir: str | Path | None = None) -> Path:
    """Unpack a .fmp archive to a directory.

    Args:
        fmp_path: Path to the .fmp file.
        target_dir: Target directory. Defaults to a temp directory.

    Returns:
        Path to the unpacked plugin directory.
    """
    fmp_path = Path(fmp_path)
    if not fmp_path.exists():
        raise FileNotFoundError(f"Plugin package not found: {fmp_path}")

    if target_dir is None:
        target_dir = Path(tempfile.mkdtemp(prefix="fm_plugin_"))
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(fmp_path, "r") as zf:
        zf.extractall(target_dir)

    # Validate after unpack
    validate_plugin(target_dir)

    logger.info("Unpacked plugin from %s → %s", fmp_path, target_dir)
    return target_dir


# ─── CLI Entry Point ───


def main() -> None:
    """CLI entry point for plugin SDK commands."""
    if len(sys.argv) < 3:
        print("Usage: python -m app.sdk.cli <command> <plugin_dir> [options]")
        print("Commands: validate, pack, unpack")
        sys.exit(1)

    command = sys.argv[1]
    plugin_path = Path(sys.argv[2])

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if command == "validate":
        manifest = validate_plugin(plugin_path)
        print(f"✅ Valid plugin: {manifest.name} v{manifest.version}")
        print(f"   Node types: {[nt.id for nt in manifest.node_types]}")
        print(f"   Permissions: {manifest.permissions or ['none']}")

    elif command == "pack":
        output = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "-o" else None
        fmp = pack_plugin(plugin_path, output)
        print(f"✅ Packed: {fmp}")

    elif command == "unpack":
        target = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "-o" else None
        unpacked = unpack_plugin(plugin_path, target)
        print(f"✅ Unpacked: {unpacked}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
