import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

# ---------------------------------------------------------------------------
# API endpointy pro kolekce.
# GET /collections/          – seznam kolekcí přístupných přihlášenému uživateli.
# GET /collections/{id}      – detail jedné kolekce (config, workflow, list_columns…).
# GET /collections/{id}/members – uživatelé pro pole typu user (číselník stanovený aplikací).
# ---------------------------------------------------------------------------

from uniforms.core.collection_deps import require_collection_access
from uniforms.core.database import get_db
from uniforms.core.security import require_auth
from uniforms.core.validation import require_slug
from uniforms.models.collection import CollectionConfig
from uniforms.models.user import User
from uniforms.services import collection_service
from uniforms.services.settings_service import get_collections_dir

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.get("/", response_model=list[CollectionConfig], summary="List accessible collections")
# Vrati seznam kolekcí dostupnych prihlasenenemu uzivateli
# system_admin vidi vse; ostatni uzivatele pouze kolekce s prirazenim v collection_roles
async def list_collections(
    current_user: User = Depends(require_auth),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[CollectionConfig]:
    col_dir = await get_collections_dir(db)
    return await collection_service.get_accessible_collections(
        db, current_user.username, current_user.role, col_dir
    )


@router.get("/{collection_id}", response_model=CollectionConfig, summary="Get collection")
# Vrati detail jedne kolekce; system_admin ma pristup vzdy, ostatni jen pri prirazeni v collection_roles
async def get_collection(
    collection_id: str,
    current_user: User = Depends(require_auth),
    db: aiosqlite.Connection = Depends(get_db),
) -> CollectionConfig:
    require_slug(collection_id, "collection_id")
    col_dir = await get_collections_dir(db)
    col = await collection_service.get_collection(collection_id, col_dir)
    if not col:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found")
    # Pro uzivatele bez role system_admin overime prirazeni v collection_roles
    if current_user.role != "system_admin":
        role = await collection_service.get_user_collection_role(
            db, current_user.username, collection_id
        )
        if not role:
            raise HTTPException(status_code=403, detail=f"No access to collection '{collection_id}'")
    return col


@router.get("/{collection_id}/members", summary="Users selectable in a `type: user` field")
# Vrati uzivatele pro pole typu user (ciselnik stanoveny aplikaci); vyzaduje pristup ke kolekci.
# source: collection_members (vychozi) | collection_admin | collection_user
async def get_collection_members(
    collection_id: str,
    source: str = collection_service.DEFAULT_USER_SOURCE,
    current_user: User = Depends(require_collection_access),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[dict]:
    col_dir = await get_collections_dir(db)
    if not (col_dir / f"{collection_id}.yaml").exists():
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found")
    try:
        return await collection_service.get_collection_members(db, collection_id, source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
