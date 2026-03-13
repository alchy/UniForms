from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel

CaseStatus = Literal["new", "open", "in_progress", "closed", "on_hold"]


class IncidentCase(BaseModel):
    case_id: str
    template_id: str
    status: CaseStatus = "new"
    created_by: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    locked_by: Optional[str] = None  # username který drží zámek (z .lock souboru)
    data: dict[str, Any] = {}        # kompletní JSON dokument (klon šablony + hodnoty analytika)


class CreateCaseRequest(BaseModel):
    template_id: str                 # vše ostatní pochází ze šablony nebo se generuje


class UpdateCaseRequest(BaseModel):
    status: Optional[CaseStatus] = None       # volitelná změna stavu workflow
    data: Optional[dict[str, Any]] = None     # volitelná aktualizace dokumentu
