import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# API endpointy pro správu rolí uživatelů v kolekcích.
# GET   /admin/collection-roles/     – všechna přiřazení uživatel→role.
# PATCH /admin/collection-roles/{id} – nahrazení přiřazení pro kolekci.
# Vyžadují system_admin.
# ---------------------------------------------------------------------------

from uniforms.core.database import get_db
from uniforms.core.security import require_admin
from uniforms.core.validation import require_slug
from uniforms.models.user import CollectionRoleId, User
from uniforms.services import collection_service
from uniforms.services.settings_service import get_collections_dir

router = APIRouter(prefix="/admin/collection-roles", tags=["Admin"])


# Jedno prirazeni uzivatele ke kolekci
class RoleAssignment(BaseModel):
    username: str
    role: CollectionRoleId


# Telo pozadavku pro hromadne nastaveni roli v kolekci
class SetRolesRequest(BaseModel):
    assignments: list[RoleAssignment]


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
    require_slug(collection_id, "collection_id")
    col_dir = await get_collections_dir(db)
    if not (col_dir / f"{collection_id}.yaml").exists():
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found")
    await collection_service.set_collection_roles(
        db, collection_id,
        [{"username": a.username, "role": a.role} for a in body.assignments],
    )
    roles = await collection_service.get_collection_roles(db, collection_id)
    return {"collection_id": collection_id, "assignments": roles}
