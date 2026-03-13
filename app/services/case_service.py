import copy
import random
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import settings


def _now_local_str() -> str:
    """Aktuální čas v nakonfigurované časové zóně (settings.timezone) ve formátu YYYY-MM-DDTHH:MM."""
    return datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%dT%H:%M")

from app.models.case import IncidentCase, UpdateCaseRequest
from app.models.template import SOCTemplate
from app.storage.base import StorageBackend


def generate_case_id(username: str = "") -> str:
    """Generuje unikátní ID incidentu ve formátu UIB-DDMMYYYY-HHMM-RRRR."""
    now = datetime.now(timezone.utc)
    rnd = random.randint(0, 9999)
    return f"UIB-{now.strftime('%d%m%Y-%H%M')}-{rnd:04d}"


def _strip_examples(obj: object) -> None:
    """
    Rekurzivně projde JSON strukturu a zpracuje pole označená is_example: true.

    Design princip:
      - V šabloně jsou příkladové hodnoty označeny is_example: true.
      - Při klonování do nového case se hodnota přesune do klíče 'example'
        (slouží jako placeholder v UI) a 'value' / 'analyst_note' se nastaví na null.
      - Hodnoty bez is_example se kopírují beze změny.
    """
    if isinstance(obj, list):
        for item in obj:
            _strip_examples(item)
    elif isinstance(obj, dict):
        if obj.get("is_example", False):
            if "value" in obj:
                # Form fields: value → example
                if obj["value"] is not None:
                    obj["example"] = obj["value"]
                    obj["value"] = None
            elif "analyst_note" in obj:
                # Checklist steps: analyst_note → example
                if obj["analyst_note"] is not None:
                    obj["example"] = obj["analyst_note"]
                    obj["analyst_note"] = None
            else:
                # Table rows: každý editovatelný string klíč → {key}_example
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


def _fill_auto_values(obj: object, auto_values: dict) -> None:
    """Rekurzivně vyplní pole označená auto_value hodnotami ze slovníku (case_id, template metadata…)."""
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


def _update_last_saved(obj: object, timestamp: str) -> None:
    """Aktualizuje všechna pole s auto_value: last_saved na aktuální timestamp."""
    if isinstance(obj, list):
        for item in obj:
            _update_last_saved(item, timestamp)
    elif isinstance(obj, dict):
        if obj.get("auto_value") == "last_saved":
            obj["value"] = timestamp
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _update_last_saved(v, timestamp)


def _clone_template_sections(sections: list) -> list:
    """
    Hluboká kopie sekcí šablony pro nový incident.
    Příkladové hodnoty jsou přesunuty do 'example' jako placeholder.
    """
    cloned = copy.deepcopy(sections)
    _strip_examples(cloned)
    return cloned


async def create_case(
    storage: StorageBackend,
    template: SOCTemplate,
    username: str,
) -> IncidentCase:
    """Vytvoří nový incident jako klon šablony a uloží ho do storage."""
    case_id = generate_case_id(username)
    now = datetime.now(timezone.utc)

    auto_values = {
        "case_id":                  case_id,
        "template_name":            template.name,
        "template_version":         template.version,
        "template_status":          template.status,
        "template_mitre_tactic":    template.mitre_tactic or "",
        "template_mitre_technique": template.mitre_technique or "",
        "template_data_sources":    ", ".join(template.data_sources) if template.data_sources else "",
        "last_saved":               _now_local_str(),
    }

    document = {
        "template_id": template.template_id,
        "template_version": template.version,
        "template_name": template.name,
        "category": template.category,
        "mitre_tactic": template.mitre_tactic,
        "mitre_technique": template.mitre_technique,
        "data_sources": template.data_sources,
        "sections": _clone_template_sections(template.sections),
    }
    _fill_auto_values(document["sections"], auto_values)

    case = IncidentCase(
        case_id=case_id,
        template_id=template.template_id,
        status="new",
        created_by=username,
        created_at=now,
        updated_at=now,
        data=document,
    )
    await storage.save_case(case)
    return case


async def list_cases(storage: StorageBackend) -> list[IncidentCase]:
    """Vrátí všechny incidenty seřazené od nejnovějšího."""
    return await storage.list_cases()


async def get_case(storage: StorageBackend, case_id: str) -> Optional[IncidentCase]:
    """Vrátí konkrétní incident dle case_id nebo None."""
    return await storage.get_case(case_id)


async def update_case(
    storage: StorageBackend,
    case_id: str,
    request: UpdateCaseRequest,
) -> Optional[IncidentCase]:
    """Aktualizuje incident – status a/nebo JSON dokument."""
    case = await storage.get_case(case_id)
    if not case:
        return None

    now = datetime.now(timezone.utc)
    if request.status is not None:
        case.status = request.status
    if request.data is not None:
        case.data = request.data
        sections = case.data.get("sections")
        if sections:
            _update_last_saved(sections, _now_local_str())
    case.updated_at = now

    await storage.save_case(case)
    return case


async def delete_case(storage: StorageBackend, case_id: str) -> bool:
    """Smaže incident. Vrátí True pokud existoval."""
    return await storage.delete_case(case_id)
