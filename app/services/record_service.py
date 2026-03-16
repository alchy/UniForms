import copy
import random
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import settings, uniforms
from app.models.collection import CollectionConfig
from app.models.record import UniRecord, UpdateRecordRequest
from app.models.template import UniTemplate
from app.storage.base import StorageBackend

# ---------------------------------------------------------------------------
# Byznysová logika pro záznamy.
# Zajišťuje generování ID záznamu dle formátu kolekce, vytváření záznamu
# z šablony (klonování + doplnění auto_value polí), aktualizaci záznamu
# (PATCH), správu workflow stavu a delegování CRUD operací na StorageBackend.
# ---------------------------------------------------------------------------

def _now_local_str() -> str:
    """Current time in configured timezone formatted as YYYY-MM-DDTHH:MM."""
    return datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%dT%H:%M")


def generate_record_id(collection: Optional[CollectionConfig] = None) -> str:
    """
    Generate a unique record ID.

    Uses collection.id_format if provided, otherwise falls back to uniforms.yaml.
    Supported tokens: {prefix}, {DDMMYYYY}, {YYYYMM}, {YYYY}, {MM}, {DD}, {HHMM}, {rand:04d}
    """
    now = datetime.now(timezone.utc)
    rnd = random.randint(0, 9999)
    if collection:
        prefix = collection.id_format.prefix
        fmt = collection.id_format.format
    else:
        prefix = uniforms.id.prefix
        fmt = uniforms.id.format

    result = fmt
    result = result.replace("{prefix}", prefix)
    result = result.replace("{DDMMYYYY}", now.strftime("%d%m%Y"))
    result = result.replace("{YYYYMM}", now.strftime("%Y%m"))
    result = result.replace("{YYYY}", now.strftime("%Y"))
    result = result.replace("{MM}", now.strftime("%m"))
    result = result.replace("{DD}", now.strftime("%d"))
    result = result.replace("{HHMM}", now.strftime("%H%M"))
    result = result.replace("{rand:04d}", f"{rnd:04d}")
    result = result.replace("{rand}", str(rnd))
    return result


def _resolve_workflow_states(collection: Optional[CollectionConfig] = None) -> list[dict]:
    """Return the workflow states for a new record from collection config or global default."""
    if collection:
        return [s.model_dump() for s in collection.workflow.states]
    return [s.model_dump() for s in uniforms.workflow.default_states]


def _resolve_initial_state(collection: Optional[CollectionConfig] = None) -> str:
    """Return the initial workflow state id from collection config or global default."""
    if collection:
        return collection.workflow.initial_state
    return uniforms.workflow.initial_state


def _build_auto_values(record_id: str, template: UniTemplate, username: str = "") -> dict:
    """
    Build the auto_value substitution map for a new record.

    Standard keys:
      case_id, record_id  → the generated record ID
      template_name       → template display name
      template_version    → template version string
      template_status     → template status (active/draft/deprecated)
      last_saved          → current local timestamp

    Extension keys (meta.*):
      meta.<key>  → value from template.meta dict (e.g. meta.mitre_tactic for SOC)
    """
    auto_values: dict = {
        "case_id": record_id,       # backwards-compat alias
        "record_id": record_id,
        "current_user": username,
        "template_name": template.name,
        "template_version": template.version,
        "template_status": template.status,
        "last_saved": _now_local_str(),
    }
    # Expose all meta fields as meta.<key>
    for key, value in template.meta.items():
        if isinstance(value, list):
            auto_values[f"meta.{key}"] = ", ".join(str(v) for v in value)
        else:
            auto_values[f"meta.{key}"] = str(value) if value is not None else ""

    # Backwards-compat auto_values for SOC (template_mitre_* etc.)
    # Supports both new style (meta: {mitre_tactic: ...}) and legacy top-level fields
    # (mitre_tactic: ... at YAML root, stored in model_extra by Pydantic).
    extra = template.model_extra or {}
    for key in ("mitre_tactic", "mitre_technique", "mitre_subtechnique", "data_sources"):
        val = template.meta.get(key) or extra.get(key)
        if val is not None:
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            str_val = str(val)
            auto_values[f"template_{key}"] = str_val
            # Also expose as meta.* if not already set from template.meta
            if f"meta.{key}" not in auto_values:
                auto_values[f"meta.{key}"] = str_val

    return auto_values


def _fill_auto_values(obj: object, auto_values: dict) -> None:
    """Recursively fill fields marked with auto_value from the substitution map."""
    if isinstance(obj, list):
        for item in obj:
            _fill_auto_values(item, auto_values)
    elif isinstance(obj, dict):
        av = obj.get("auto_value")
        if av and av in auto_values:
            obj["value"] = auto_values[av]
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _fill_auto_values(v, auto_values)


def _strip_examples(obj: object) -> None:
    """
    Recursively process example values: move them to the 'example' placeholder
    and clear the actual value so the form starts empty.
    """
    if isinstance(obj, list):
        for item in obj:
            _strip_examples(item)
    elif isinstance(obj, dict):
        if obj.get("is_example", False):
            if "value" in obj:
                if obj["value"] is not None:
                    obj["example"] = obj["value"]
                    obj["value"] = None
            elif "analyst_note" in obj:
                if obj["analyst_note"] is not None:
                    obj["example"] = obj["analyst_note"]
                    obj["analyst_note"] = None
            else:
                _SYSTEM_KEYS = {
                    "id", "is_example", "system_role", "when_to_contact",
                    "type", "title", "action", "done",
                }
                for key in list(obj.keys()):
                    if key not in _SYSTEM_KEYS and not key.endswith("_example"):
                        if obj[key] is not None:
                            obj[key + "_example"] = obj[key]
                            obj[key] = None
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _strip_examples(v)


def _update_last_saved(obj: object, timestamp: str) -> None:
    """Update all fields with auto_value: last_saved to the current timestamp."""
    if isinstance(obj, list):
        for item in obj:
            _update_last_saved(item, timestamp)
    elif isinstance(obj, dict):
        if obj.get("auto_value") == "last_saved":
            obj["value"] = timestamp
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _update_last_saved(v, timestamp)


async def create_record(
    storage: StorageBackend,
    template: UniTemplate,
    username: str,
    collection_id: str = "",
    collection: Optional[CollectionConfig] = None,
) -> UniRecord:
    """Create a new record as a clone of the given template and persist it."""
    record_id = generate_record_id(collection)
    now = datetime.now(timezone.utc)

    workflow_states = _resolve_workflow_states(collection)
    initial_state = _resolve_initial_state(collection)
    auto_values = _build_auto_values(record_id, template, username)

    sections = copy.deepcopy(template.sections)
    _strip_examples(sections)
    _fill_auto_values(sections, auto_values)

    document = {
        "template_id": template.template_id,
        "template_name": template.name,
        "template_version": template.version,
        "category": template.category,
        "meta": template.meta,
        # Workflow states are embedded in the document so the record is
        # self-contained even if the template changes later.
        "workflow_states": workflow_states,
        "sections": sections,
    }

    record = UniRecord(
        record_id=record_id,
        collection_id=collection_id,
        template_id=template.template_id,
        status=initial_state,
        created_by=username,
        created_at=now,
        updated_at=now,
        data=document,
    )
    await storage.save_record(record)
    return record


async def list_records(storage: StorageBackend) -> list[UniRecord]:
    return await storage.list_records()


async def get_record(storage: StorageBackend, record_id: str) -> Optional[UniRecord]:
    return await storage.get_record(record_id)


async def update_record(
    storage: StorageBackend,
    record_id: str,
    request: UpdateRecordRequest,
) -> Optional[UniRecord]:
    record = await storage.get_record(record_id)
    if not record:
        return None

    now = datetime.now(timezone.utc)
    if request.status is not None:
        record.status = request.status
    if request.data is not None:
        record.data = request.data
        sections = record.data.get("sections")
        if sections:
            _update_last_saved(sections, _now_local_str())
    record.updated_at = now

    await storage.save_record(record)
    return record


async def delete_record(storage: StorageBackend, record_id: str) -> bool:
    return await storage.delete_record(record_id)
