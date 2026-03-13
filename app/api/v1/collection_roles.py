from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.core.database import get_db
from app.core.security import require_admin
from app.models.user import User
from app.services import collection_service
from app.services.settings_service import get_setting

router = APIRouter(prefix="/admin/collection-roles", tags=["Admin"])


# Jedno prirazeni uzivatele ke kolekci; role je collection_admin nebo collection_user
class RoleAssignment(BaseModel):
    username: str
    role: str  # "collection_admin" nebo "collection_user"


# Telo pozadavku pro hromadne nastaveni roli v kolekci
class SetRolesRequest(BaseModel):
    assignments: list[RoleAssignment]


# Nacte cestu k adresari kolekcí z DB nastaveni, nebo pouzije vychozi hodnotu
async def _collections_dir(db: aiosqlite.Connection) -> Path:
    return Path(await get_setting(db, "collections_dir") or settings.default_collections_dir)


@router.get("/", summary="All collection role assignments (admin)")
# Vrati vsechna prirazeni collection_roles z DB; vyzaduje roli system_admin
async def list_all_roles(
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[dict]:
    async with db.execute(
        "SELECT username, collection_id, role FROM collection_roles ORDER BY collection_id, username"
    ) as cursor:
        rows = await cursor.fetchall()
    return [{"username": row[0], "collection_id": row[1], "role": row[2]} for row in rows]


@router.patch("/{collection_id}", summary="Set collection roles (admin)")
# Nahradi vsechna prirazeni roli pro danou kolekci; vyzaduje roli system_admin
async def set_roles(
    collection_id: str,
    body: SetRolesRequest,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    col_dir = await _collections_dir(db)
    if not (col_dir / f"{collection_id}.yaml").exists():
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found")
    await collection_service.set_collection_roles(
        db, collection_id,
        [{"username": a.username, "role": a.role} for a in body.assignments],
    )
    roles = await collection_service.get_collection_roles(db, collection_id)
    return {"collection_id": collection_id, "assignments": roles}
