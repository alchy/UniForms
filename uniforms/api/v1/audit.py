from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from uniforms import config
from uniforms.core import audit
from uniforms.core.security import require_admin
from uniforms.models.user import User

# ---------------------------------------------------------------------------
# Čtení auditní stopy (data/audit/RRRR-MM-DD.jsonl) – pouze system_admin.
# Zápis dělá AuditMiddleware; tady se jen filtruje a vrací, nejnovější první.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/admin/audit", tags=["Audit"])

_DAY = r"^\d{4}-\d{2}-\d{2}$"


@router.get("/", summary="Audit events, newest first (system_admin)")
async def list_audit_events(
    day_from: Optional[str] = Query(None, pattern=_DAY, description="YYYY-MM-DD (default: 7 days ago)"),
    day_to: Optional[str] = Query(None, pattern=_DAY, description="YYYY-MM-DD (default: today)"),
    who: Optional[str] = Query(None, max_length=128, description="substring of actor/subject"),
    kind: Optional[Literal["auth", "write"]] = None,
    outcome: Optional[Literal["ok", "denied", "rejected", "error"]] = None,
    collection_id: Optional[str] = Query(None, max_length=64),
    text: Optional[str] = Query(None, max_length=128, description="free-text substring"),
    limit: int = Query(500, ge=1, le=5000),
    current_user: User = Depends(require_admin),
) -> dict:
    today = datetime.now(timezone.utc).date()
    day_to = day_to or today.isoformat()
    day_from = day_from or (today - timedelta(days=7)).isoformat()
    events = audit.read_events(
        config.settings.audit_dir, day_from, day_to, limit=limit,
        who=who, kind=kind, outcome=outcome, collection_id=collection_id, text=text,
    )
    return {
        "day_from": day_from,
        "day_to": day_to,
        "count": len(events),
        "truncated": len(events) >= limit,
        "retention_days": config.settings.audit_retention_days,
        "events": events,
    }
