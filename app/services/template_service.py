import copy
import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional

import yaml
import aiosqlite
from fastapi import Depends

from app.config import settings
from app.core.database import get_db
from app.models.template import UniTemplate
from app.services.settings_service import get_setting

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template normalization
#
# Allows writing templates in a shorthand format:
#   - fields without 'type' default to "text"
#   - fields without 'editable' default to true
#   - fields without 'value' default to null
#   - checklist steps as plain strings → auto-expanded to {action: ...}
#   - steps and groups without 'id' → ID generated from title or position
#   - sections without 'id' → ID generated from title or type
#
# Full format (existing templates) is preserved unchanged (backwards-compatible).
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s\-]+", "_", text)
    return text or "item"


def _norm_column(col: dict) -> dict:
    """Normalize a v2 column definition dict ({key, label, type, options, editable})."""
    col.setdefault("type", "text")
    col.setdefault("editable", False)
    return col


def _norm_field(field: dict) -> dict:
    # v2 shorthand: auto: <source>  →  auto_value: <source> + editable: false
    if "auto" in field:
        field["auto_value"] = field.pop("auto")
        field["editable"] = False
    field.setdefault("type", "text")
    field.setdefault("editable", True)
    if "example" in field:
        field["is_example"] = True
        field["value"] = field.pop("example")
    field.setdefault("value", None)
    return field


def _norm_step(step, idx: int, prefix: str) -> dict:
    if isinstance(step, str):
        step = {"action": step}
    if "example" in step:
        step["is_example"] = True
        step["analyst_note"] = step.pop("example")
    step.setdefault("id", f"{prefix}_{idx + 1:02d}")
    step.setdefault("analyst_note", None)
    step.setdefault("done", False)
    return step


def _norm_group(group: dict, idx: int, section_id: str) -> dict:
    group_id = group.get("id") or _slugify(group.get("title") or f"group_{idx + 1}")
    group["id"] = group_id
    prefix = f"{section_id}_{group_id}"
    group["steps"] = [
        _norm_step(s, i, prefix) for i, s in enumerate(group.get("steps", []))
    ]
    return group


_SECTION_TYPE_ALIASES = {
    "fields": "form",
}


def _norm_section(section: dict, idx: int) -> dict:
    title = section.get("title", "")
    section_id = section.get("id") or _slugify(
        title or section.get("type", f"section_{idx + 1}")
    )
    section["id"] = section_id

    # Normalize type aliases (e.g. "fields" → "form")
    if section.get("type") in _SECTION_TYPE_ALIASES:
        section["type"] = _SECTION_TYPE_ALIASES[section["type"]]

    if "fields" in section:
        section["fields"] = [_norm_field(f) for f in section["fields"]]

    # v2: flat steps list → step_groups wrapper with null title
    if "steps" in section and "step_groups" not in section:
        section["step_groups"] = [{"title": None, "steps": section.pop("steps")}]

    if "step_groups" in section:
        section["step_groups"] = [
            _norm_group(g, i, section_id)
            for i, g in enumerate(section["step_groups"])
        ]

    # v2: columns as list of dicts → normalize each column dict
    cols = section.get("columns")
    if cols and isinstance(cols, list) and cols and isinstance(cols[0], dict):
        section["columns"] = [_norm_column(c) for c in cols]

    if "subsections" in section:
        section["subsections"] = [
            _norm_section(sub, i) for i, sub in enumerate(section["subsections"])
        ]
    return section


def _normalize_template(data: dict) -> dict:
    if "sections" in data and isinstance(data["sections"], list):
        data["sections"] = [
            _norm_section(s, i) for i, s in enumerate(data["sections"])
        ]
    return data


# ---------------------------------------------------------------------------
# Template inheritance resolver
# ---------------------------------------------------------------------------

def _resolve_extends(data: dict, all_dirs: list[Path]) -> dict:
    """
    If the template declares 'extends: <parent_template_id>', find the parent
    in any of the given directories and prepend its sections to the child's sections.

    The child's metadata fields (name, category, meta, workflow, etc.) are preserved.
    Abstract parents are found even though they don't appear in list_templates().
    """
    parent_id = data.get("extends")
    if not parent_id:
        return data

    parent_data = None
    for template_dir in all_dirs:
        for yaml_file in template_dir.glob("*.yaml"):
            try:
                candidate = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if candidate and candidate.get("template_id") == parent_id:
                    parent_data = candidate
                    break
            except Exception:
                pass
        if parent_data is not None:
            break

    if parent_data is None:
        logger.warning(
            "Template '%s' extends '%s' but parent was not found",
            data.get("template_id"), parent_id,
        )
        return data

    # Recursively resolve parent's own inheritance
    parent_data = _resolve_extends(parent_data, all_dirs)

    # Merge: parent sections first, then child sections
    parent_sections = copy.deepcopy(parent_data.get("sections", []))
    child_sections = data.get("sections", [])
    data["sections"] = parent_sections + child_sections

    # Remove the extends key from the resolved template
    data.pop("extends", None)
    return data


# ---------------------------------------------------------------------------
# TemplateService
# ---------------------------------------------------------------------------

class TemplateService:
    """
    Access to YAML templates for a single collection.
    Separated from StorageBackend – templates have their own CRUD without locking.

    All templates live in one directory: {schemas_dir}/{collection_id}/
    """

    def __init__(self, collection_dir: Path) -> None:
        self.collection_dir = collection_dir
        collection_dir.mkdir(parents=True, exist_ok=True)

    def _all_yaml_files(self) -> list[Path]:
        return sorted(self.collection_dir.glob("*.yaml"))

    async def list_templates(self) -> list[UniTemplate]:
        """Return all non-abstract templates in the collection directory."""
        result = []
        for yaml_file in self._all_yaml_files():
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not data:
                    continue
                if data.get("abstract", False):
                    continue
                data = _resolve_extends(data, [self.collection_dir])
                data = _normalize_template(data)
                result.append(UniTemplate(**data, filename=yaml_file.name))
            except Exception as exc:
                logger.warning("Cannot load template '%s': %s", yaml_file.name, exc)
        return result

    async def get_template(self, template_id: str) -> Optional[UniTemplate]:
        """Return a template by ID (including abstract templates for inheritance)."""
        for yaml_file in self._all_yaml_files():
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not data or data.get("template_id") != template_id:
                    continue
                data = _resolve_extends(data, [self.collection_dir])
                data = _normalize_template(data)
                return UniTemplate(**data, filename=yaml_file.name)
            except Exception as exc:
                logger.warning("Cannot load template '%s': %s", yaml_file.name, exc)
        return None

    def _find_file(self, template_id: str) -> Optional[Path]:
        for yaml_file in self._all_yaml_files():
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if data and data.get("template_id") == template_id:
                    return yaml_file
            except Exception:
                pass
        return None

    async def get_source(self, template_id: str) -> Optional[dict]:
        """Return {'content': str, 'filename': str} or None."""
        path = self._find_file(template_id)
        if not path:
            return None
        return {"content": path.read_text(encoding="utf-8"), "filename": path.name}

    async def save(self, template_id: str, content: str) -> str:
        """Validate YAML and overwrite existing template file. Returns filename."""
        yaml.safe_load(content)  # raises ValueError if invalid YAML
        path = self._find_file(template_id)
        if not path:
            raise FileNotFoundError(f"Template '{template_id}' not found")
        path.write_text(content, encoding="utf-8")
        return path.name

    async def create(self, filename: str, content: str) -> str:
        """Validate YAML and create a new template in the collection directory."""
        data = yaml.safe_load(content)  # raises ValueError if invalid YAML
        if not filename.endswith(".yaml"):
            filename += ".yaml"
        target = self.collection_dir / filename
        if target.exists():
            raise FileExistsError(f"File '{filename}' already exists")
        target.write_text(content, encoding="utf-8")
        return data.get("template_id", filename.replace(".yaml", ""))

    async def delete(self, template_id: str) -> None:
        """Delete a template file."""
        path = self._find_file(template_id)
        if not path:
            raise FileNotFoundError(f"Template '{template_id}' not found")
        path.unlink()


async def get_template_service(
    collection_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> TemplateService:
    """
    FastAPI dependency – returns a TemplateService scoped to the given collection.
    FastAPI automatically resolves `collection_id` from the URL path parameter.
    """
    schemas_dir = Path(
        await get_setting(db, "schemas_dir") or settings.default_schemas_dir
    )
    return TemplateService(schemas_dir / collection_id)
