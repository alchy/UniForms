import logging
from pathlib import Path

import yaml

from app.extensions.base import Extension

logger = logging.getLogger(__name__)

_extensions: list[Extension] = []


def load_extensions(extension_refs) -> list[Extension]:
    """
    Load extensions from the list of ExtensionRef objects defined in uniforms.yaml.
    Called once at application startup from main.py.
    """
    global _extensions
    loaded = []
    for ref in extension_refs:
        ext_path = Path(ref.path)
        manifest_path = ext_path / "extension.yaml"
        if not manifest_path.exists():
            logger.warning("Extension '%s': manifest not found at '%s'", ref.id, manifest_path)
            continue
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            ext = Extension(
                id=data.get("id", ref.id),
                name=data.get("name", ref.id),
                version=data.get("version", "1.0"),
                path=ext_path,
                js_files=data.get("js", []),
                section_types=data.get("section_types", []),
                auto_values=data.get("auto_values", []),
                templates_dir=data.get("templates_dir"),
            )
            loaded.append(ext)
            logger.info("Loaded extension '%s' v%s from '%s'", ext.name, ext.version, ext_path)
        except Exception as exc:
            logger.error("Failed to load extension '%s': %s", ref.id, exc)

    _extensions = loaded
    return loaded


def get_extensions() -> list[Extension]:
    """Return the list of currently loaded extensions."""
    return _extensions
