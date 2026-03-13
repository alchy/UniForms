from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.core.database import get_db
from app.core.security import require_auth
from app.models.collection import CollectionConfig
from app.models.user import User
from app.services import collection_service
from app.services.settings_service import get_setting

router = APIRouter(prefix="/collections", tags=["Collections"])


# Nacte cestu k adresari kolekcí z DB nastaveni, nebo pouzije vychozi hodnotu z konfigurace
async def _collections_dir(db: aiosqlite.Connection) -> Path:
    return Path(await get_setting(db, "collections_dir") or settings.default_collections_dir)


@router.get("/", response_model=list[CollectionConfig], summary="List accessible collections")
# Vrati seznam kolekcí dostupnych prihlasenenemu uzivateli
# system_admin vidi vse; ostatni uzivatele pouze kolekce s prirazenim v collection_roles
async def list_collections(
    current_user: User = Depends(require_auth),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[CollectionConfig]:
    col_dir = await _collections_dir(db)
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
    col_dir = await _collections_dir(db)
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
