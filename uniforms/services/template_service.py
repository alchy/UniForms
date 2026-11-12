import copy
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

import yaml
import aiosqlite
from fastapi import Depends

from uniforms.core.database import get_db
from uniforms.core.validation import SLUG_RE, require_slug
from uniforms.models.template import UniTemplate
from uniforms.services.settings_service import get_schemas_dir

# ---------------------------------------------------------------------------
# Služba pro načítání a správu YAML šablon.
# TemplateService obsluhuje jednu kolekci (adresář {schemas_dir}/{collection_id}).
# Zajišťuje normalizaci zkratkového zápisu v2 (auto, example, flat steps…),
# dědičnost šablon (extends), CRUD operace (list, get, save, create, delete)
# a FastAPI dependency get_template_service() pro injekci do route handlerů.
# ---------------------------------------------------------------------------

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

def atomic_write_text(path: Path, content: str) -> None:
    """Write a file through a temporary sibling + rename, so readers never see a partial file."""
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


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
    if field["type"] == "user":             # app-defined list: users of the collection
        field.setdefault("source", "collection_members")
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


def _norm_section(section: dict, idx: int) -> dict:
    title = section.get("title", "")
    section_id = section.get("id") or _slugify(
        title or section.get("type", f"section_{idx + 1}")
    )
    section["id"] = section_id

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

def section_effective_id(section: dict, idx: int = 0) -> str:
    """Id a section is known by: its `id`, else a slug of its title, else of its type.

    The one rule shared by the resolver, the normalizer and the Designer, so that
    `override:` / `remove:` refer to the same sections everywhere.
    """
    title = section.get("title") or ""
    return str(section.get("id") or _slugify(str(title or section.get("type") or f"section_{idx + 1}")))


#: Child-section keys that change an inherited section instead of adding one
OVERRIDE_KEY = "override"     # {override: <id>, ...section}  – replace it, in place, for this form only
REMOVE_KEY = "remove"         # {remove: <id>}                – drop it from this form
USE_KEY = "use"               # {use: <template_id>#<section id>, id?: <new id>} – embed one block (live link)
                              # {override: <id>, use: <ref>}  – replace an inherited block by another one


def parse_block_ref(ref) -> Optional[tuple[str, str]]:
    """'zoo-blocks-v1#ringing' → ('zoo-blocks-v1', 'ringing'); None when malformed."""
    if not isinstance(ref, str) or ref.count("#") != 1:
        return None
    tid, sid = (part.strip() for part in ref.split("#"))
    return (tid, sid) if tid and sid else None


def resolve_block(ref, all_dirs: list[Path], seen: Optional[set] = None) -> tuple[Optional[dict], Optional[str]]:
    """Find the block a `use:` points to. Returns ({'section', 'origin', 'index', 'id'}, None)
    or (None, error message). Only blocks DEFINED in that template can be used – not ones it
    inherits or embeds itself – so a reference never chains through further references."""
    parsed = parse_block_ref(ref)
    if not parsed:
        return None, f"'{ref}' is not a block reference – expected <template_id>#<section id>"
    tid, sid = parsed
    if seen and tid in seen:
        return None, f"'{ref}' refers to this template itself or to one that embeds it – that would be a cycle"
    source = _find_template(tid, all_dirs)
    if source is None:
        return None, f"'{ref}': template '{tid}' not found"
    for entry in resolve_sections(source, all_dirs, (seen or set()) | {tid}):
        if entry["id"] == sid and entry["state"] in ("own", "overridden") and entry["origin"] == tid:
            return {"section": copy.deepcopy(entry["section"]), "origin": tid,
                    "index": entry["index"], "id": sid}, None
    return None, f"'{ref}': template '{tid}' defines no block '{sid}'"


def _find_template(template_id: str, all_dirs: list[Path]) -> Optional[dict]:
    for template_dir in all_dirs:
        for yaml_file in template_dir.glob("*.yaml"):
            try:
                candidate = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if isinstance(candidate, dict) and candidate.get("template_id") == template_id:
                    return candidate
            except Exception:
                pass
    return None


def resolve_sections(data: dict, all_dirs: list[Path], _seen: Optional[set] = None) -> list[dict]:
    """Final section list of a template with the origin of every section.

    Returns [{'section', 'origin', 'index', 'state', 'id'}] where origin is the template_id
    that defines the section, index its position in that template's `sections` list, and
    state is 'inherited' | 'overridden' | 'replaced' | 'embedded' | 'own'.
    `use:` entries are resolved to a copy of the referenced block (live – re-read on
    every resolve); a broken reference is skipped with a warning.
    Removed inherited sections are returned with state 'removed' (the caller drops them).

    Order: the parent's sections (recursively resolved), with `override:` replacing a
    section in place and `remove:` dropping it; then the child's other sections as written.
    A plain child section is always added – sharing an id with a parent section does NOT
    replace it (kept for backward compatibility; the Designer warns about it).
    """
    own_id = data.get("template_id")
    seen = set(_seen or ())
    if own_id:
        seen.add(own_id)
    result: list[dict] = []
    parent_id = data.get("extends")
    if parent_id:
        if parent_id in seen:
            logger.error("Template '%s': inheritance cycle through '%s' – parent ignored", own_id, parent_id)
        else:
            parent = _find_template(parent_id, all_dirs)
            if parent is None:
                logger.warning("Template '%s' extends '%s' but parent was not found", own_id, parent_id)
            else:
                for entry in resolve_sections(parent, all_dirs, seen):
                    if entry["state"] == "removed":
                        continue
                    # from this template's point of view everything of the parent is inherited
                    result.append({"section": copy.deepcopy(entry["section"]), "origin": entry["origin"],
                                   "index": entry["index"], "state": "inherited", "id": entry["id"]})
    by_id = {e["id"]: e for e in result}
    for i, sec in enumerate(data.get("sections") or []):
        if isinstance(sec, dict) and REMOVE_KEY in sec and len(sec) == 1:
            target = by_id.get(str(sec[REMOVE_KEY]))
            if target is None:
                logger.warning("Template '%s': remove '%s' – no such inherited section", own_id, sec[REMOVE_KEY])
            else:
                target["state"] = "removed"
            continue
        if isinstance(sec, dict) and OVERRIDE_KEY in sec:
            target_id = str(sec[OVERRIDE_KEY])
            target = by_id.get(target_id)
            if target is None:
                logger.warning("Template '%s': override '%s' – no such inherited section", own_id, target_id)
                continue
            if USE_KEY in sec:                 # replace the inherited block by another block
                block, error = resolve_block(sec[USE_KEY], all_dirs, seen)
                if block is None:
                    logger.warning("Template '%s': override '%s' – %s", own_id, target_id, error)
                    continue
                block["section"]["id"] = target_id
                target.update(section=block["section"], origin=block["origin"], index=block["index"], state="replaced")
                continue
            replacement = {k: v for k, v in sec.items() if k != OVERRIDE_KEY}
            replacement.setdefault("id", target_id)
            target.update(section=replacement, origin=own_id, index=i, state="overridden")
            continue
        if isinstance(sec, dict) and USE_KEY in sec:
            block, error = resolve_block(sec[USE_KEY], all_dirs, seen)
            if block is None:
                logger.warning("Template '%s': use – %s", own_id, error)
                continue
            if sec.get("id"):
                block["section"]["id"] = str(sec["id"])
                block["id"] = str(sec["id"])
            result.append({**block, "state": "embedded"})
            continue
        result.append({"section": sec, "origin": own_id, "index": i, "state": "own",
                       "id": section_effective_id(sec, i) if isinstance(sec, dict) else f"section_{i + 1}"})
    return result


def _resolve_extends(data: dict, all_dirs: list[Path]) -> dict:
    """
    Resolve inheritance: the parent's sections first (with this template's `override:` /
    `remove:` applied), then this template's own sections. See resolve_sections().

    The child's metadata fields (name, category, meta, workflow, etc.) are preserved.
    Abstract parents are found even though they don't appear in list_templates().
    """
    if not data.get("extends") and not any(
        isinstance(s, dict) and (OVERRIDE_KEY in s or REMOVE_KEY in s or USE_KEY in s) for s in data.get("sections") or []
    ):
        return data
    data["sections"] = [e["section"] for e in resolve_sections(data, all_dirs) if e["state"] != "removed"]
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

    async def list_templates(self, include_abstract: bool = False) -> list[UniTemplate]:
        """Return templates in the collection directory.

        Abstract templates (bases for inheritance) are skipped unless
        ``include_abstract`` is set – records cannot be created from them, so only
        editors (template management page) ask for them. Each returned template
        keeps its direct parent id in ``extends`` (the resolver drops it otherwise).
        """
        result = []
        for yaml_file in self._all_yaml_files():
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not data:
                    continue
                if data.get("abstract", False) and not include_abstract:
                    continue
                parent_id = data.get("extends")
                data = _resolve_extends(data, [self.collection_dir])
                data = _normalize_template(data)
                data["extends"] = parent_id
                result.append(UniTemplate(**data, filename=yaml_file.name))
            except Exception as exc:
                logger.warning("Cannot load template '%s': %s", yaml_file.name, exc)
        return result

    async def get_template(self, template_id: str) -> Optional[UniTemplate]:
        """Return a template by ID (including abstract templates for inheritance)."""
        yaml_file = self._find_file(template_id)
        if not yaml_file:
            return None
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
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

    @staticmethod
    def _parse_yaml(content: str) -> dict:
        """Parse YAML content; raises ValueError with a readable message when invalid."""
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML: {exc}") from exc

    def _validate(self, content: str, filename: str) -> dict:
        """Parse YAML and make sure it loads as a template (incl. extends/normalisation).

        Raises ValueError with a readable message, so a broken template is rejected
        on save instead of silently disappearing from the template list.
        """
        data = self._parse_yaml(content)
        if not isinstance(data, dict):
            raise ValueError("Template YAML must be a mapping")
        if not data.get("template_id"):
            raise ValueError("Template YAML must contain 'template_id'")
        try:
            resolved = _resolve_extends(copy.deepcopy(data), [self.collection_dir])
            UniTemplate(**_normalize_template(resolved), filename=filename)
        except Exception as exc:
            raise ValueError(f"Invalid template: {exc}") from exc
        return data

    async def save(self, template_id: str, content: str) -> str:
        """Validate YAML and overwrite existing template file. Returns filename."""
        path = self._find_file(template_id)
        if not path:
            raise FileNotFoundError(f"Template '{template_id}' not found")
        data = self._validate(content, path.name)
        if data["template_id"] != template_id:
            raise ValueError(
                f"template_id cannot be changed on save ('{template_id}' → '{data['template_id']}'); "
                "create a new template instead"
            )
        atomic_write_text(path, content)
        return path.name

    async def create(self, filename: str, content: str) -> str:
        """
        Validate YAML and create a new template in the collection directory.

        `filename` is a slug WITHOUT the .yaml suffix (validated – path traversal guard).
        """
        filename = filename.removesuffix(".yaml")
        if not SLUG_RE.match(filename):
            raise ValueError(
                "Invalid filename – only lowercase letters, digits, '_' and '-' are allowed"
            )
        data = self._validate(content, f"{filename}.yaml")
        if self._find_file(data["template_id"]):
            raise FileExistsError(f"Template '{data['template_id']}' already exists")
        target = self.collection_dir / f"{filename}.yaml"
        if target.exists():
            raise FileExistsError(f"File '{filename}.yaml' already exists")
        atomic_write_text(target, content)
        return data["template_id"]

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
    require_slug(collection_id, "collection_id")
    schemas_dir = await get_schemas_dir(db)
    return TemplateService(schemas_dir / collection_id)
