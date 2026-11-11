"""Collection Designer – model ↔ YAML conversion, validation and safe saving.

The designer GUI never edits YAML text. It works with a *model*: the plain dict
that ``yaml.safe_load`` returns for a collection or template file – NOT the
normalized structure. Because the model is the raw dict, everything the designer
has no control for (unknown keys, shorthand such as ``auto:`` / ``example:`` /
flat ``steps:``) survives a load → edit → save round trip untouched.

This module has no dependency on the HTTP layer and can be used from scripts::

    from pathlib import Path
    from uniforms.services import designer_service as ds

    loaded = ds.load_collection(Path("data/collections"), "zoo")
    loaded["model"]["name"] = "Zoo"
    ds.save_collection(Path("data/collections"), "zoo", loaded["model"],
                       base_hash=loaded["source"]["hash"], confirm_rewrite=True)

Saving rules (the YAML files stay the source of truth):

* the server-side validators stay authoritative – ``parse_collection_yaml`` for
  collections, ``TemplateService`` (``_validate`` / ``save`` / ``create``) for
  templates; the designer lint only adds friendlier, earlier messages,
* a save that changes nothing semantically does not touch the file,
* PyYAML cannot keep comments. A file whose comments / anchors would be lost is
  only rewritten after an explicit ``confirm_rewrite``; the leading comment block
  of the file is kept and the previous version goes to ``.designer_backup/``,
* ``base_hash`` (hash of the source the editor loaded) guards against
  overwriting a file that changed on disk in the meantime.
"""
from __future__ import annotations

import copy
import hashlib
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from uniforms.core.validation import SAFE_ID_RE, SLUG_RE
from uniforms.models.template import UniTemplate
from uniforms.services import collection_service
from uniforms.services.record_service import _strip_examples
from uniforms.services.template_service import (
    TemplateService, _normalize_template, _resolve_extends, _slugify,
)

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = ".designer_backup"
BACKUP_KEEP = 10
_MAX_SAFE_INT = 2 ** 53 - 1


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class DesignerError(Exception):
    """Base class – ``code`` is a stable machine-readable identifier."""

    code = "designer_error"

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra


class DesignerNotFound(DesignerError):
    code = "not_found"


class DesignerExists(DesignerError):
    code = "exists"


class DesignerStale(DesignerError):
    """The file changed on disk since the editor loaded it (base_hash mismatch)."""
    code = "stale"


class DesignerRewriteNotConfirmed(DesignerError):
    """Saving would drop comments / anchors and the caller did not confirm it."""
    code = "rewrite_not_confirmed"


class DesignerUnsupported(DesignerError):
    """The YAML holds values the JSON-based designer cannot carry losslessly."""
    code = "unsupported"


class DesignerInvalid(DesignerError):
    """Validation failed; ``issues`` lists every problem found."""
    code = "invalid"

    def __init__(self, message: str, issues: Optional[list[dict]] = None) -> None:
        super().__init__(message)
        self.issues = issues or []


# ---------------------------------------------------------------------------
# Catalog – what the designer palette and attribute panel offer.
# Single source of truth for the GUI (served by GET /admin/designer/catalog).
# ---------------------------------------------------------------------------

SECTION_TYPES = [
    {"type": "header", "label": "Header", "icon": "bi-card-heading", "children": "fields",
     "top_level_only": True,
     "description": "Record header – info grid with automatic and editable fields."},
    {"type": "form", "label": "Form", "icon": "bi-ui-checks-grid", "children": "fields",
     "description": "Form section with fields."},
    {"type": "checklist", "label": "Checklist", "icon": "bi-list-check", "children": "steps",
     "description": "Procedure steps with checkboxes, optionally in groups."},
    {"type": "table", "label": "Table", "icon": "bi-table", "children": "columns",
     "description": "Editable table with typed columns."},
    {"type": "section_group", "label": "Section group", "icon": "bi-collection",
     "children": "subsections", "top_level_only": True,
     "description": "Accordion grouping several sections under one title."},
]
FIELD_TYPES = [
    {"type": "text", "label": "Text", "icon": "bi-input-cursor-text"},
    {"type": "textarea", "label": "Long text", "icon": "bi-textarea-resize"},
    {"type": "select", "label": "Select", "icon": "bi-menu-button-wide"},
    {"type": "datetime", "label": "Date & time", "icon": "bi-calendar-event"},
    {"type": "number", "label": "Number", "icon": "bi-123"},
]
COLUMN_TYPES = ["text", "select", "textarea"]
AUTO_SOURCES = [
    {"value": "record_id", "label": "Record ID"},
    {"value": "template_name", "label": "Template name"},
    {"value": "template_version", "label": "Template version"},
    {"value": "current_user", "label": "User who created the record"},
    {"value": "now", "label": "Time of creation"},
    {"value": "last_saved", "label": "Time of last save"},
]
STATE_COLORS = ["secondary", "primary", "info", "warning", "success", "danger", "dark"]
TEMPLATE_STATUSES = ["active", "draft", "deprecated"]
ROLE_IDS = ["collection_admin", "collection_user"]
TAKE_OVER_VALUE_TYPES = ["username", "timestamp"]
ID_TOKENS = ["{prefix}", "{YYYYMM}", "{DDMMYYYY}", "{YYYY}", "{MM}", "{DD}", "{HHMM}",
             "{rand:04d}", "{rand}"]
TERMINOLOGY_KEYS = [
    "record_id_label", "records_subtitle", "templates_subtitle", "dashboard_subtitle",
    "new_record_btn", "record_owner_label", "take_over_btn",
    "status_active", "status_draft", "status_deprecated",
]


def catalog(terminology_defaults: Optional[dict] = None) -> dict:
    """Everything the GUI needs to build its palette and attribute controls."""
    defaults = terminology_defaults or {}
    return {
        "section_types": copy.deepcopy(SECTION_TYPES),
        "field_types": copy.deepcopy(FIELD_TYPES),
        "column_types": list(COLUMN_TYPES),
        "auto_sources": copy.deepcopy(AUTO_SOURCES),
        "state_colors": list(STATE_COLORS),
        "template_statuses": list(TEMPLATE_STATUSES),
        "role_ids": list(ROLE_IDS),
        "take_over_value_types": list(TAKE_OVER_VALUE_TYPES),
        "id_tokens": list(ID_TOKENS),
        "terminology_keys": [
            {"key": k, "default": str(defaults.get(k, ""))} for k in TERMINOLOGY_KEYS
        ],
    }


# ---------------------------------------------------------------------------
# YAML dumping
# ---------------------------------------------------------------------------

class _Dumper(yaml.SafeDumper):
    """Block style, indented sequences, no anchors, literal blocks for multi-line text."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def ignore_aliases(self, data):
        return True


def _represent_str(dumper: yaml.SafeDumper, value: str):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_str)


def _dump(data: Any) -> str:
    return yaml.dump(
        data, Dumper=_Dumper, default_flow_style=False, sort_keys=False,
        allow_unicode=True, width=110, indent=2,
    )


def dump_yaml(model: dict, header: str = "") -> str:
    """Serialize a model to canonical YAML.

    Key order is kept. Top-level blocks and template sections are separated by a
    blank line for readability. The result is verified to parse back to an equal
    dict – a dumper surprise therefore can never reach the disk.
    """
    if not isinstance(model, dict):
        raise DesignerInvalid("Model must be a mapping")
    parts: list[str] = []
    prev_block = False
    for key, value in model.items():
        is_block = isinstance(value, (dict, list)) and bool(value)
        if key == "sections" and is_block and all(isinstance(s, dict) and s for s in value):
            items = [_dump({key: [s]}).split("\n", 1)[1].rstrip("\n") for s in value]
            piece = f"{_dump({key: None}).split(':')[0]}:\n" + "\n\n".join(items) + "\n"
        else:
            piece = _dump({key: value})
        if parts and (is_block or prev_block):
            parts.append("\n")
        parts.append(piece)
        prev_block = is_block
    text = "".join(parts) if parts else "{}\n"
    if yaml.safe_load(text) != model:  # pragma: no cover – safety net
        text = _dump(model)
        if yaml.safe_load(text) != model:
            raise DesignerUnsupported("Model cannot be represented as YAML without loss")
    return header + text


# ---------------------------------------------------------------------------
# Source analysis (comments, anchors, canonical form, JSON safety)
# ---------------------------------------------------------------------------

def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _split_header(content: str) -> str:
    """Leading block of comment / blank lines – kept verbatim when the file is rewritten."""
    lines = content.splitlines(keepends=True)
    end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            end = i + 1
        elif stripped:
            break
    else:
        return ""  # nothing but comments – no document to attach a header to
    header = "".join(lines[:end])
    if header and not header.endswith("\n"):
        header += "\n"
    return header


def _count_comments_and_anchors(content: str) -> tuple[int, int]:
    """Count comment lines and anchors/aliases using the YAML scanner.

    A ``#`` starts a comment only outside scalars, so the scalar token spans are
    excluded – ``color: "#ff0000"`` or ``label: Issue #3`` are not comments.
    """
    spans: list[tuple[int, int]] = []
    anchors = 0
    try:
        for token in yaml.scan(content):
            if isinstance(token, yaml.ScalarToken):
                spans.append((token.start_mark.index, token.end_mark.index))
            elif isinstance(token, (yaml.AnchorToken, yaml.AliasToken)):
                anchors += 1
    except yaml.YAMLError:
        return 0, 0
    comment_lines: set[int] = set()
    span_i = 0
    line_no = 0
    for match in re.finditer(r"#|\n", content):
        pos = match.start()
        if match.group() == "\n":
            line_no += 1
            continue
        if pos > 0 and content[pos - 1] not in " \t\n":
            continue
        while span_i < len(spans) and spans[span_i][1] <= pos:
            span_i += 1
        if span_i < len(spans) and spans[span_i][0] <= pos < spans[span_i][1]:
            continue
        comment_lines.add(line_no)
    return len(comment_lines), anchors


def json_unsafe_reason(data: Any, path: str = "") -> Optional[str]:
    """Return why ``data`` cannot travel through JSON to the browser and back, or None."""
    if data is None or isinstance(data, (str, bool)):
        return None
    if isinstance(data, int):
        return None if abs(data) <= _MAX_SAFE_INT else f"{path or 'value'}: integer too large"
    if isinstance(data, float):
        return None if math.isfinite(data) else f"{path or 'value'}: non-finite number"
    if isinstance(data, list):
        for i, item in enumerate(data):
            reason = json_unsafe_reason(item, f"{path}[{i}]")
            if reason:
                return reason
        return None
    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(key, str):
                return f"{path or 'mapping'}: key {key!r} is not a string"
            reason = json_unsafe_reason(value, f"{path}.{key}" if path else key)
            if reason:
                return reason
        return None
    return f"{path or 'value'}: unsupported YAML type {type(data).__name__} (e.g. unquoted date)"


def analyze_source(content: str, data: Any) -> dict:
    """Describe a YAML source for the designer.

    hash            – sha256 of the text; sent back as ``base_hash`` on save
    comments        – number of comment lines in the file
    comments_lost   – comment lines that a designer save would drop (all but the header)
    anchors         – YAML anchors/aliases (expanded on save)
    canonical       – True when the file already is in the designer's output format
    rewrite_lossy   – True when saving needs ``confirm_rewrite``
    """
    header = _split_header(content)
    comments, anchors = _count_comments_and_anchors(content)
    header_comments = sum(1 for line in header.splitlines() if line.strip().startswith("#"))
    comments_lost = max(0, comments - header_comments)
    canonical = False
    if isinstance(data, dict) and json_unsafe_reason(data) is None:
        try:
            canonical = dump_yaml(data, header) == content
        except DesignerError:
            canonical = False
    return {
        "hash": content_hash(content),
        "comments": comments,
        "comments_lost": comments_lost,
        "anchors": anchors,
        "canonical": canonical,
        "rewrite_lossy": comments_lost > 0 or anchors > 0,
    }


def _parse_for_designer(content: str, what: str) -> dict:
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise DesignerUnsupported(
            f"{what} is not valid YAML – fix it in the raw YAML editor first ({exc})"
        )
    if not isinstance(data, dict):
        raise DesignerUnsupported(f"{what} is not a YAML mapping – use the raw YAML editor")
    reason = json_unsafe_reason(data)
    if reason:
        raise DesignerUnsupported(
            f"{what} holds a value the designer cannot edit safely ({reason}) – "
            "use the raw YAML editor"
        )
    return data


def _check_model(model: Any) -> dict:
    if not isinstance(model, dict):
        raise DesignerInvalid("Model must be a mapping")
    reason = json_unsafe_reason(model)
    if reason:
        raise DesignerInvalid(f"Model holds an unsupported value ({reason})")
    return model


# ---------------------------------------------------------------------------
# File helpers (atomic write, backups)
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _backup(path: Path) -> Optional[str]:
    """Copy the current file to ``.designer_backup/`` next to it; returns the backup name."""
    if not path.exists():
        return None
    backup_dir = path.parent / BACKUP_DIR_NAME
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = backup_dir / f"{path.stem}.{stamp}.yaml"
    target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    old = sorted(backup_dir.glob(f"{path.stem}.*.yaml"))
    for stale in old[:-BACKUP_KEEP]:
        try:
            stale.unlink()
        except OSError:  # pragma: no cover
            pass
    return target.name


def _changed_keys(old: Any, new: dict) -> list[str]:
    """Names of top-level keys that differ – key names only, safe for the audit trail."""
    old = old if isinstance(old, dict) else {}
    keys = [k for k in new if k not in old or old[k] != new[k]]
    keys += [k for k in old if k not in new]
    return [str(k)[:64] for k in keys][:40]


def _issue(level: str, path: str, message: str) -> dict:
    return {"level": level, "path": path, "message": message}


def _errors(issues: list[dict]) -> list[dict]:
    return [i for i in issues if i["level"] == "error"]


def _raise_on_errors(issues: list[dict]) -> None:
    errors = _errors(issues)
    if errors:
        first = errors[0]
        where = f"{first['path']}: " if first["path"] else ""
        more = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
        raise DesignerInvalid(f"{where}{first['message']}{more}", issues)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

def _collection_path(collections_dir: Path, collection_id: str) -> Path:
    if not SLUG_RE.match(collection_id or ""):
        raise DesignerInvalid(
            "Invalid collection id – only lowercase letters, digits, '_' and '-' are allowed"
        )
    return collections_dir / f"{collection_id}.yaml"


def new_collection_model(collection_id: str = "", name: str = "") -> dict:
    """Starting point for a new collection (a complete, valid definition)."""
    return {
        "id": collection_id,
        "name": name,
        "description": "",
        "workflow": {
            "initial_state": "new",
            "states": [
                {"id": "new", "label": "New", "color": "secondary"},
                {"id": "in_progress", "label": "In progress", "color": "warning"},
                {"id": "closed", "label": "Closed", "color": "success"},
            ],
        },
        "id_format": {"prefix": "REC", "format": "{prefix}-{YYYYMM}-{rand:04d}"},
        "list_columns": [{"key": "record_owner", "label": "Record owner"}],
        "roles": [
            {"id": "collection_admin", "label": "Collection admin"},
            {"id": "collection_user", "label": "Collection user"},
        ],
        "title_field": "title",
    }


def lint_collection(model: dict, known_field_keys: Optional[set[str]] = None) -> list[dict]:
    """Designer-level checks of a collection model. Errors block saving, warnings inform."""
    issues: list[dict] = []
    if not isinstance(model.get("name"), str) or not model.get("name", "").strip():
        issues.append(_issue("error", "name", "Collection name is required"))

    wf = model.get("workflow")
    if wf is not None and not isinstance(wf, dict):
        issues.append(_issue("error", "workflow", "Workflow must be a mapping"))
        wf = None
    if wf is not None:
        states = wf.get("states")
        if states is not None:
            if not isinstance(states, list) or not states:
                issues.append(_issue("error", "workflow.states", "At least one workflow state is required"))
            else:
                seen: set[str] = set()
                for i, st in enumerate(states):
                    p = f"workflow.states[{i}]"
                    if not isinstance(st, dict):
                        issues.append(_issue("error", p, "State must be a mapping"))
                        continue
                    sid = st.get("id")
                    if not isinstance(sid, str) or not sid.strip():
                        issues.append(_issue("error", p, "State id is required"))
                    elif not SAFE_ID_RE.match(sid):
                        issues.append(_issue("error", p, f"State id '{sid}' may only contain letters, digits, '_' and '-'"))
                    elif sid in seen:
                        issues.append(_issue("error", p, f"Duplicate state id '{sid}'"))
                    else:
                        seen.add(sid)
                    if not isinstance(st.get("label"), str) or not st.get("label", "").strip():
                        issues.append(_issue("error", p, "State label is required"))

    roles = model.get("roles")
    if roles is not None:
        if not isinstance(roles, list):
            issues.append(_issue("error", "roles", "Roles must be a list"))
        else:
            seen_roles: set[str] = set()
            for i, role in enumerate(roles):
                rid = role.get("id") if isinstance(role, dict) else None
                if rid not in ROLE_IDS:
                    issues.append(_issue("error", f"roles[{i}]",
                                         f"Role id must be one of: {', '.join(ROLE_IDS)}"))
                elif rid in seen_roles:
                    issues.append(_issue("error", f"roles[{i}]", f"Duplicate role '{rid}'"))
                else:
                    seen_roles.add(rid)

    cols = model.get("list_columns")
    if cols is not None:
        if not isinstance(cols, list):
            issues.append(_issue("error", "list_columns", "List columns must be a list"))
        else:
            for i, col in enumerate(cols):
                p = f"list_columns[{i}]"
                if not isinstance(col, dict) or not str(col.get("key") or "").strip():
                    issues.append(_issue("error", p, "Column key is required"))
                    continue
                if not str(col.get("label") or "").strip():
                    issues.append(_issue("error", p, "Column label is required"))
                if known_field_keys is not None and known_field_keys and col["key"] not in known_field_keys:
                    issues.append(_issue("warning", p,
                                         f"No template of this collection has a field '{col['key']}' – the column will be empty"))

    idf = model.get("id_format")
    if isinstance(idf, dict) and isinstance(idf.get("format"), str):
        leftover = idf["format"]
        for token in sorted(ID_TOKENS, key=len, reverse=True):
            leftover = leftover.replace(token, "")
        if "{" in leftover or "}" in leftover:
            issues.append(_issue("warning", "id_format.format",
                                 "Format contains an unknown token – it will appear literally in record IDs"))
        if "{rand" not in idf["format"]:
            issues.append(_issue("warning", "id_format.format",
                                 "Format has no {rand} token – record IDs may collide"))

    take_over = model.get("take_over")
    if take_over is not None:
        if not isinstance(take_over, dict) or not str(take_over.get("field") or "").strip():
            issues.append(_issue("error", "take_over", "Take over needs a target field key"))
        else:
            if take_over.get("value_type", "username") not in TAKE_OVER_VALUE_TYPES:
                issues.append(_issue("warning", "take_over.value_type",
                                     f"Unknown value type – supported: {', '.join(TAKE_OVER_VALUE_TYPES)}"))
            if known_field_keys and take_over["field"] not in known_field_keys:
                issues.append(_issue("warning", "take_over.field",
                                     f"No template of this collection has a field '{take_over['field']}'"))

    title_field = model.get("title_field")
    if title_field and known_field_keys and title_field not in known_field_keys:
        issues.append(_issue("warning", "title_field",
                             f"No template of this collection has a field '{title_field}' – the template name is used as the title"))

    term = model.get("terminology")
    if isinstance(term, dict):
        for key in term:
            if key not in TERMINOLOGY_KEYS:
                issues.append(_issue("warning", f"terminology.{key}",
                                     "Not one of the documented per-collection terminology keys"))
    return issues


def check_collection(model: dict, collection_id: str,
                     known_field_keys: Optional[set[str]] = None) -> dict:
    """Dry run: lint + strict validation. Returns {'ok', 'yaml', 'issues'} – never writes."""
    issues: list[dict] = []
    text = ""
    try:
        _check_model(model)
        issues = lint_collection(model, known_field_keys)
        text = dump_yaml(model)
        collection_service.parse_collection_yaml(text, collection_id)
    except DesignerError as exc:
        issues.append(_issue("error", "", exc.message))
    except ValueError as exc:
        issues.append(_issue("error", "", str(exc)))
    return {"ok": not _errors(issues), "yaml": text, "issues": issues}


def load_collection(collections_dir: Path, collection_id: str) -> Optional[dict]:
    """Load a collection for editing: {'collection_id', 'filename', 'model', 'source'} or None."""
    path = _collection_path(collections_dir, collection_id)
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    model = _parse_for_designer(content, f"Collection '{collection_id}'")
    return {
        "collection_id": collection_id,
        "filename": path.name,
        "model": model,
        "source": analyze_source(content, model),
    }


def save_collection(
    collections_dir: Path,
    collection_id: str,
    model: dict,
    *,
    create: bool = False,
    base_hash: Optional[str] = None,
    confirm_rewrite: bool = False,
    known_field_keys: Optional[set[str]] = None,
) -> dict:
    """Validate and write a collection model.

    Returns {'collection_id', 'filename', 'change', 'changed_keys', 'backup',
    'comments_discarded', 'issues', 'source'} where change is
    'created' | 'updated' | 'unchanged'.
    """
    path = _collection_path(collections_dir, collection_id)
    _check_model(model)
    exists = path.exists()
    if create and exists:
        raise DesignerExists(f"Collection '{collection_id}' already exists")
    if not create and not exists:
        raise DesignerNotFound(f"Collection '{collection_id}' not found")

    old_content = path.read_text(encoding="utf-8") if exists else ""
    old_data = None
    if exists:
        if base_hash and base_hash != content_hash(old_content):
            raise DesignerStale(
                f"Collection '{collection_id}' changed on disk since it was opened – reload it"
            )
        try:
            old_data = yaml.safe_load(old_content)
        except yaml.YAMLError:
            old_data = None

    issues = lint_collection(model, known_field_keys)
    _raise_on_errors(issues)

    header = _split_header(old_content) if exists else ""
    text = dump_yaml(model, header)
    try:
        collection_service.parse_collection_yaml(text, collection_id)
    except ValueError as exc:
        raise DesignerInvalid(str(exc), issues + [_issue("error", "", str(exc))])

    result = {
        "collection_id": collection_id, "filename": path.name, "issues": issues,
        "changed_keys": [], "backup": None, "comments_discarded": 0,
    }
    if exists and old_data == model:
        result["change"] = "unchanged"
        result["source"] = analyze_source(old_content, model)
        return result

    if exists:
        info = analyze_source(old_content, old_data)
        if info["rewrite_lossy"] and not confirm_rewrite:
            raise DesignerRewriteNotConfirmed(
                f"Saving rewrites '{path.name}' and drops {info['comments_lost']} comment line(s)"
                + (f" and {info['anchors']} YAML anchor(s)" if info["anchors"] else "")
                + " – confirm to continue",
                comments_lost=info["comments_lost"], anchors=info["anchors"],
            )
        result["comments_discarded"] = info["comments_lost"]
        result["backup"] = _backup(path)
        result["changed_keys"] = _changed_keys(old_data, model)
    else:
        collections_dir.mkdir(parents=True, exist_ok=True)

    _atomic_write(path, text)
    result["change"] = "updated" if exists else "created"
    result["source"] = analyze_source(text, model)
    return result


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def new_template_model(template_id: str = "", name: str = "") -> dict:
    """Starting point for a new template: header with the usual automatic fields."""
    return {
        "template_id": template_id,
        "name": name,
        "version": "1.0",
        "status": "draft",
        "description": "",
        "sections": [
            {
                "id": "header", "title": "Header", "type": "header",
                "fields": [
                    {"key": "record_id", "label": "Record ID", "auto": "record_id"},
                    {"key": "template_name", "label": "Template", "auto": "template_name"},
                    {"key": "title", "label": "Title"},
                    {"key": "record_owner", "label": "Record owner"},
                ],
            },
        ],
    }


def _raw_templates(collection_dir: Path) -> list[tuple[Path, Any]]:
    out = []
    if not collection_dir.is_dir():
        return out
    for path in sorted(collection_dir.glob("*.yaml")):
        try:
            out.append((path, yaml.safe_load(path.read_text(encoding="utf-8"))))
        except Exception:
            out.append((path, None))
    return out


def _walk_sections(sections: Any):
    """Yield every section dict including section_group children."""
    for sec in sections if isinstance(sections, list) else []:
        if isinstance(sec, dict):
            yield sec
            yield from _walk_sections(sec.get("subsections"))


def list_templates(collection_dir: Path) -> list[dict]:
    """All template files of a collection incl. abstract ones (raw metadata, not normalized)."""
    result = []
    for path, data in _raw_templates(collection_dir):
        if not isinstance(data, dict) or not data.get("template_id"):
            result.append({
                "filename": path.name, "template_id": None, "name": path.stem,
                "loadable": False, "abstract": False, "extends": None, "status": None,
                "version": None, "sections": 0,
            })
            continue
        result.append({
            "filename": path.name,
            "template_id": str(data.get("template_id")),
            "name": str(data.get("name") or ""),
            "status": data.get("status", "active"),
            "version": None if data.get("version") is None else str(data.get("version")),
            "abstract": bool(data.get("abstract", False)),
            "extends": data.get("extends") or None,
            "sections": len(data.get("sections") or []) if isinstance(data.get("sections"), list) else 0,
            "loadable": json_unsafe_reason(data) is None,
        })
    return result


def collection_field_keys(collection_dir: Path) -> list[dict]:
    """Field keys used by the collection's templates – for list_columns / title_field pickers."""
    found: dict[str, str] = {}
    for _path, data in _raw_templates(collection_dir):
        if not isinstance(data, dict):
            continue
        for sec in _walk_sections(data.get("sections")):
            for field in sec.get("fields") or []:
                if isinstance(field, dict) and isinstance(field.get("key"), str):
                    found.setdefault(field["key"], str(field.get("label") or ""))
    return [{"key": k, "label": v} for k, v in sorted(found.items())]


def _parent_chain(collection_dir: Path, parent_id: Any, own_id: Any) -> tuple[list[str], Optional[str]]:
    """Follow ``extends`` upwards. Returns (chain of ids, error message or None)."""
    by_id = {
        str(d.get("template_id")): d
        for _p, d in _raw_templates(collection_dir)
        if isinstance(d, dict) and d.get("template_id")
    }
    chain: list[str] = []
    current = parent_id
    while current:
        current = str(current)
        if current == str(own_id) or current in chain:
            return chain, f"Inheritance cycle: '{current}' extends itself through its parents"
        if current not in by_id:
            return chain, f"Parent template '{current}' does not exist in this collection"
        chain.append(current)
        current = by_id[current].get("extends")
    return chain, None


def _effective_id(section: dict, idx: int) -> str:
    title = section.get("title") or ""
    return str(section.get("id") or _slugify(str(title or section.get("type") or f"section_{idx + 1}")))


def _lint_fields(fields: Any, path: str, issues: list[dict]) -> None:
    if not isinstance(fields, list):
        issues.append(_issue("error", path, "'fields' must be a list"))
        return
    keys: set[str] = set()
    for i, field in enumerate(fields):
        p = f"{path}[{i}]"
        if not isinstance(field, dict):
            issues.append(_issue("error", p, "Field must be a mapping"))
            continue
        key = field.get("key")
        if not isinstance(key, str) or not key.strip():
            issues.append(_issue("error", p, "Field key is required"))
        elif key in keys:
            issues.append(_issue("warning", p, f"Duplicate field key '{key}' in this section"))
        else:
            keys.add(key)
        if not str(field.get("label") or "").strip():
            issues.append(_issue("warning", p, "Field has no label"))
        ftype = field.get("type", "text")
        if ftype not in [t["type"] for t in FIELD_TYPES]:
            issues.append(_issue("warning", p, f"Unknown field type '{ftype}' – rendered as text"))
        if ftype == "select" and not field.get("options"):
            issues.append(_issue("warning", p, "Select field has no options"))
        if field.get("options") is not None and not isinstance(field.get("options"), list):
            issues.append(_issue("error", p, "'options' must be a list"))
        if "auto" in field and "auto_value" in field:
            issues.append(_issue("warning", p, "Both 'auto' and 'auto_value' are set – 'auto' wins"))
    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            continue
        for cond in ("visible_if", "required_if"):
            expr = field.get(cond)
            if isinstance(expr, str):
                for ref in re.findall(r"([A-Za-z_][\w]*)\s*(?:==|!=)", expr):
                    if ref not in keys:
                        issues.append(_issue("warning", f"{path}[{i}]",
                                             f"{cond} refers to '{ref}', which is not a field of this section"))


def _lint_section(section: Any, path: str, issues: list[dict], nested: bool) -> None:
    if not isinstance(section, dict):
        issues.append(_issue("error", path, "Section must be a mapping"))
        return
    stype = section.get("type")
    known = [t["type"] for t in SECTION_TYPES]
    if not section.get("title") and not section.get("id"):
        issues.append(_issue("warning", path, "Section has neither a title nor an id"))
    if stype not in known:
        issues.append(_issue("warning", path, f"Unknown section type '{stype}' – shown as raw data unless a custom renderer is registered"))
    if nested and stype in ("header", "section_group"):
        issues.append(_issue("warning", path, f"A '{stype}' section inside a section group is not supported by the renderer"))
    if "fields" in section:
        _lint_fields(section["fields"], f"{path}.fields", issues)
    if stype == "table":
        cols = section.get("columns")
        if not isinstance(cols, list) or not cols:
            issues.append(_issue("warning", path, "Table has no columns"))
        elif isinstance(cols[0], dict):
            seen: set[str] = set()
            for i, col in enumerate(cols):
                p = f"{path}.columns[{i}]"
                if not isinstance(col, dict) or not str(col.get("key") or "").strip():
                    issues.append(_issue("error", p, "Column key is required"))
                    continue
                if col["key"] in seen:
                    issues.append(_issue("warning", p, f"Duplicate column key '{col['key']}'"))
                seen.add(col["key"])
                if col.get("type", "text") == "select" and not col.get("options"):
                    issues.append(_issue("warning", p, "Select column has no options"))
        for key in ("rows",):
            if section.get(key) is not None and not isinstance(section.get(key), list):
                issues.append(_issue("error", f"{path}.{key}", f"'{key}' must be a list"))
    if stype == "checklist":
        if "steps" in section and "step_groups" in section:
            issues.append(_issue("warning", path, "Both 'steps' and 'step_groups' are set – 'steps' is ignored"))
        groups = section.get("step_groups")
        if groups is not None and not isinstance(groups, list):
            issues.append(_issue("error", f"{path}.step_groups", "'step_groups' must be a list"))
            groups = None
        step_lists = [(f"{path}.steps", section.get("steps"))] if "steps" in section else []
        for gi, group in enumerate(groups or []):
            if not isinstance(group, dict):
                issues.append(_issue("error", f"{path}.step_groups[{gi}]", "Step group must be a mapping"))
                continue
            step_lists.append((f"{path}.step_groups[{gi}].steps", group.get("steps", [])))
        for spath, steps in step_lists:
            if not isinstance(steps, list):
                issues.append(_issue("error", spath, "'steps' must be a list"))
                continue
            for si, step in enumerate(steps):
                action = step if isinstance(step, str) else (step.get("action") if isinstance(step, dict) else None)
                if not isinstance(step, (str, dict)):
                    issues.append(_issue("error", f"{spath}[{si}]", "Step must be text or a mapping"))
                elif not str(action or "").strip():
                    issues.append(_issue("warning", f"{spath}[{si}]", "Step has no action text"))
    if stype == "section_group":
        if "sections" in section and "subsections" not in section:
            issues.append(_issue("warning", path, "Children of a section group must be under 'subsections' – 'sections' is not rendered"))
        subs = section.get("subsections")
        if subs is not None and not isinstance(subs, list):
            issues.append(_issue("error", f"{path}.subsections", "'subsections' must be a list"))
        else:
            for i, sub in enumerate(subs or []):
                _lint_section(sub, f"{path}.subsections[{i}]", issues, nested=True)


def lint_template(model: dict, collection_dir: Optional[Path] = None) -> list[dict]:
    """Designer-level checks of a template model. Errors block saving, warnings inform."""
    issues: list[dict] = []
    tid = model.get("template_id")
    if not isinstance(tid, str) or not tid.strip():
        issues.append(_issue("error", "template_id", "Template id is required"))
    elif not SAFE_ID_RE.match(tid):
        issues.append(_issue("error", "template_id", "Template id may only contain letters, digits, '_' and '-'"))
    if not isinstance(model.get("name"), str) or not model.get("name", "").strip():
        issues.append(_issue("error", "name", "Template name is required"))
    if "version" in model and not isinstance(model["version"], str):
        issues.append(_issue("error", "version", "Version must be text (e.g. '1.0')"))
    if model.get("status", "active") not in TEMPLATE_STATUSES:
        issues.append(_issue("warning", "status", f"Unknown status – expected one of: {', '.join(TEMPLATE_STATUSES)}"))
    if model.get("extends"):
        if collection_dir is not None:
            _chain, error = _parent_chain(collection_dir, model["extends"], tid)
            if error:
                issues.append(_issue("error", "extends", error))
    sections = model.get("sections", [])
    if not isinstance(sections, list):
        issues.append(_issue("error", "sections", "'sections' must be a list"))
        return issues
    seen: dict[str, str] = {}
    for i, sec in enumerate(sections):
        path = f"sections[{i}]"
        _lint_section(sec, path, issues, nested=False)
        if isinstance(sec, dict):
            eff = _effective_id(sec, i)
            if eff in seen:
                issues.append(_issue("warning", path, f"Section id '{eff}' is also used by {seen[eff]}"))
            else:
                seen[eff] = path
    if not sections and not model.get("extends"):
        issues.append(_issue("warning", "sections", "Template has no sections"))
    return issues


def _preview_sections(model: dict, collection_dir: Path) -> list:
    """Sections as a freshly created record would show them (extends + normalize + examples).

    Works on a deep copy – the normalizer mutates its input (pops ``auto`` / ``example`` /
    ``steps``) and must never touch the model that is going to be written.
    """
    data = _resolve_extends(copy.deepcopy(model), [collection_dir])
    data = _normalize_template(data)
    template = UniTemplate(**data)
    sections = copy.deepcopy(template.sections)
    _strip_examples(sections)

    def fill_auto(obj: Any) -> None:
        if isinstance(obj, list):
            for item in obj:
                fill_auto(item)
        elif isinstance(obj, dict):
            if obj.get("auto_value") and obj.get("value") is None:
                obj["value"] = f"‹{obj['auto_value']}›"
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    fill_auto(value)

    fill_auto(sections)
    return sections


def check_template(collection_dir: Path, model: dict, *, filename: str = "preview.yaml") -> dict:
    """Dry run for the editor: lint + strict validation + preview. Never writes.

    Returns {'ok', 'yaml', 'issues', 'sections'}; ``sections`` is the normalized form
    (incl. inherited sections) ready for the client renderer, or [] when invalid.
    """
    issues: list[dict] = []
    text = ""
    sections: list = []
    try:
        _check_model(model)
        issues = lint_template(model, collection_dir)
        text = dump_yaml(model)
        TemplateService(collection_dir)._validate(text, filename)
        sections = _preview_sections(model, collection_dir)
    except DesignerError as exc:
        issues.append(_issue("error", "", exc.message))
    except Exception as exc:
        issues.append(_issue("error", "", str(exc)))
    return {"ok": not _errors(issues), "yaml": text, "issues": issues, "sections": sections}


async def load_template(collection_dir: Path, template_id: str) -> Optional[dict]:
    """Load a template for editing.

    Returns {'template_id', 'filename', 'model', 'source', 'inherited'} or None;
    ``inherited`` lists the parents' sections (read-only context for the canvas).
    """
    svc = TemplateService(collection_dir)
    source = await svc.get_source(template_id)
    if not source:
        return None
    model = _parse_for_designer(source["content"], f"Template '{template_id}'")
    return {
        "template_id": template_id,
        "filename": source["filename"],
        "model": model,
        "source": analyze_source(source["content"], model),
        "inherited": inherited_sections(collection_dir, model.get("extends"), template_id),
    }


def inherited_sections(collection_dir: Path, parent_id: Any, own_id: Any = None) -> dict:
    """Raw sections contributed by the parent chain: {'chain': [...], 'sections': [...], 'error'}."""
    if not parent_id:
        return {"chain": [], "sections": [], "error": None}
    chain, error = _parent_chain(collection_dir, parent_id, own_id)
    if error:
        return {"chain": chain, "sections": [], "error": error}
    resolved = _resolve_extends({"extends": str(parent_id), "sections": []}, [collection_dir])
    sections = resolved.get("sections", [])
    if json_unsafe_reason(sections):
        return {"chain": chain, "sections": [], "error": "Parent template cannot be shown in the designer"}
    return {"chain": chain, "sections": sections, "error": None}


async def save_template(
    collection_dir: Path,
    model: dict,
    *,
    template_id: Optional[str] = None,
    filename: Optional[str] = None,
    base_hash: Optional[str] = None,
    confirm_rewrite: bool = False,
) -> dict:
    """Validate and write a template model.

    ``template_id`` set → update that template (its id cannot change);
    ``template_id`` None → create a new file ``filename`` (slug without .yaml).

    Returns {'template_id', 'filename', 'change', 'changed_keys', 'backup',
    'comments_discarded', 'issues', 'source'}.
    """
    _check_model(model)
    svc = TemplateService(collection_dir)
    issues = lint_template(model, collection_dir)
    result = {"issues": issues, "changed_keys": [], "backup": None, "comments_discarded": 0}

    if template_id is None:
        _raise_on_errors(issues)
        fname = (filename or "").removesuffix(".yaml")
        text = dump_yaml(model)
        try:
            new_id = await svc.create(fname, text)
        except FileExistsError as exc:
            raise DesignerExists(str(exc))
        except ValueError as exc:
            raise DesignerInvalid(str(exc), issues + [_issue("error", "", str(exc))])
        result.update(template_id=new_id, filename=f"{fname}.yaml", change="created",
                      source=analyze_source(text, model))
        return result

    source = await svc.get_source(template_id)
    if not source:
        raise DesignerNotFound(f"Template '{template_id}' not found")
    old_content = source["content"]
    path = collection_dir / source["filename"]
    if base_hash and base_hash != content_hash(old_content):
        raise DesignerStale(f"Template '{template_id}' changed on disk since it was opened – reload it")
    if model.get("template_id") != template_id:
        raise DesignerInvalid(
            f"template_id cannot be changed on save ('{template_id}' → '{model.get('template_id')}'); "
            "create a new template instead"
        )
    _raise_on_errors(issues)
    old_data = yaml.safe_load(old_content)
    result.update(template_id=template_id, filename=source["filename"])
    if old_data == model:
        result.update(change="unchanged", source=analyze_source(old_content, model))
        return result

    info = analyze_source(old_content, old_data)
    if info["rewrite_lossy"] and not confirm_rewrite:
        raise DesignerRewriteNotConfirmed(
            f"Saving rewrites '{source['filename']}' and drops {info['comments_lost']} comment line(s)"
            + (f" and {info['anchors']} YAML anchor(s)" if info["anchors"] else "")
            + " – confirm to continue",
            comments_lost=info["comments_lost"], anchors=info["anchors"],
        )
    text = dump_yaml(model, _split_header(old_content))
    try:
        svc._validate(text, source["filename"])
    except ValueError as exc:
        raise DesignerInvalid(str(exc), issues + [_issue("error", "", str(exc))])
    backup = _backup(path)
    try:
        await svc.save(template_id, text)
    except ValueError as exc:  # pragma: no cover – validated above
        raise DesignerInvalid(str(exc), issues)
    result.update(change="updated", backup=backup, comments_discarded=info["comments_lost"],
                  changed_keys=_changed_keys(old_data, model), source=analyze_source(text, model))
    return result
