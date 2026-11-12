from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, status

# ---------------------------------------------------------------------------
# API endpointy pro runtime nastavení aplikace. Vyžadují roli system_admin.
# GET   /settings/      – vrátí všechna editovatelná nastavení (slovník klíč→hodnota).
# PATCH /settings/      – aktualizuje jeden nebo více klíčů (records_dir, schemas_dir, collections_dir,
#                         designer_enabled, time_zone, date_format, time_format).
# Zadaný adresář musí fyzicky existovat, jinak endpoint vrátí HTTP 422.
# Časové pásmo musí být platné IANA jméno; časy se ukládají v UTC, nastavení mění jen zobrazení.
# ---------------------------------------------------------------------------

from uniforms.core.database import get_db
from uniforms.core.security import require_admin
from uniforms.models.user import User
from uniforms.services.settings_service import (
    BOOL_SETTINGS, TIME_SETTING_KEYS, get_all_settings, get_bool_setting, load_time_settings,
    set_setting, validate_time_setting,
)

router = APIRouter(prefix="/settings", tags=["Settings"])

# Pouze tato nastaveni lze menit pres GUI; branding a terminologie jsou v uniforms.yaml
_ALLOWED_KEYS = {"records_dir", "schemas_dir", "collections_dir", *BOOL_SETTINGS, *TIME_SETTING_KEYS}


@router.get("/", summary="Current path settings (admin)")
# Vrati vsechna aktualni nastaveni ulozena v SQLite; vyzaduje roli system_admin
async def get_settings(
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict[str, str]:
    current = await get_all_settings(db)
    for key in BOOL_SETTINGS:
        current[key] = "true" if await get_bool_setting(db, key) else "false"
    current.update(await load_time_settings(db))      # effective values incl. defaults
    return current


@router.patch("/", summary="Update path settings (admin)")
# Aktualizuje nastaveni cest; ignoruje nezname klice a overuje existenci adresare; vyzaduje system_admin
async def update_settings(
    request: Request,
    updates: dict[str, str],
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict[str, str]:
    request.state.audit = {"changed": sorted(updates)[:20]}   # names only
    for key, value in updates.items():
        if key not in _ALLOWED_KEYS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown setting '{key}'. Allowed: {', '.join(sorted(_ALLOWED_KEYS))}",
            )
        if key in BOOL_SETTINGS:
            if value not in ("true", "false"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Value for '{key}' must be 'true' or 'false'.",
                )
            await set_setting(db, key, value)
            continue
        if key in TIME_SETTING_KEYS:
            error = validate_time_setting(key, value)
            if error:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)
            await set_setting(db, key, value)
            await load_time_settings(db)          # pages pick the new values up at once
            continue
        if not value or not value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Value for '{key}' must not be empty.",
            )
        try:
            p = Path(value)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Value for '{key}' is not a valid path.",
            )
        if ".." in p.parts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Value for '{key}' must not contain '..'.",
            )
        if not p.exists():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Directory '{value}' does not exist.",
            )
        await set_setting(db, key, value)
    return await get_all_settings(db)
