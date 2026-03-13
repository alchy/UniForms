from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class UniRecord(BaseModel):
    record_id: str
    collection_id: str
    template_id: str
    status: str = "new"                  # validated at runtime against workflow states
    created_by: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    locked_by: Optional[str] = None      # username holding the lock (from .lock file)
    data: dict[str, Any] = {}            # full document (cloned template + user edits)


class CreateRecordRequest(BaseModel):
    template_id: str                     # everything else comes from the template or is generated


class UpdateRecordRequest(BaseModel):
    status: Optional[str] = None         # optional workflow state change
    data: Optional[dict[str, Any]] = None
