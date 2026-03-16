from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status

# ---------------------------------------------------------------------------
# API endpointy pro runtime nastavení aplikace. Vyžadují roli system_admin.
# GET   /settings/      – vrátí všechna editovatelná nastavení (slovník klíč→hodnota).
# PATCH /settings/      – aktualizuje jeden nebo více klíčů (records_dir, schemas_dir, collections_dir).
# Zadaný adresář musí fyzicky existovat, jinak endpoint vrátí HTTP 400.
# ---------------------------------------------------------------------------

from app.core.database import get_db
from app.core.security import require_admin
from app.models.user import User
from app.services.settings_service import get_all_settings, set_setting

router = APIRouter(prefix="/settings", tags=["Settings"])

# Pouze tato nastaveni lze menit pres GUI; branding a terminologie jsou v uniforms.yaml
_ALLOWED_KEYS = {"records_dir", "schemas_dir", "collections_dir"}


@router.get("/", summary="Current path settings (admin)")
# Vrati vsechna aktualni nastaveni ulozena v SQLite; vyzaduje roli system_admin
async def get_settings(
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict[str, str]:
    return await get_all_settings(db)


@router.patch("/", summary="Update path settings (admin)")
# Aktualizuje nastaveni cest; ignoruje nezname klice a overuje existenci adresare; vyzaduje system_admin
async def update_settings(
    updates: dict[str, str],
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict[str, str]:
    for key, value in updates.items():
        if key not in _ALLOWED_KEYS:
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
