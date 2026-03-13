import re
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import aiosqlite
from app.core.database import get_db
from app.core.security import require_admin
from app.models.user import User
from app.services import collection_service
from app.services.settings_service import get_setting
from app.config import settings as app_settings

router = APIRouter(prefix="/admin/collections", tags=["Admin – Collections"])

# Regex pro validaci nazvu souboru kolekce (jen male pismena, cislice, _ a -)
_SLUG_RE = re.compile(r"^[a-z0-9_-]+$")


# Nacte cestu k adresari kolekcí z DB nastaveni, nebo pouzije vychozi hodnotu
async def _collections_dir(db: aiosqlite.Connection) -> Path:
    d = await get_setting(db, "collections_dir") or app_settings.default_collections_dir
    return Path(d)


# --- Modely ---


class CollectionCreate(BaseModel):
    filename: str   # bez pripony .yaml
    content: str


class CollectionUpdate(BaseModel):
    content: str


# --- Endpointy ---


@router.get("/", summary="List all collections (admin)")
# Vrati seznam vsech kolekcí ze souboru YAML; vyzaduje roli system_admin
async def list_collections(
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[dict]:
    d = await _collections_dir(db)
    cols = await collection_service.list_collections(d)
    return [c.model_dump() for c in cols]


@router.get("/{collection_id}/source", summary="Get raw YAML of a collection (admin)")
# Vrati surovy YAML obsah souboru kolekce pro editor; vyzaduje roli system_admin
async def get_collection_source(
    collection_id: str,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    d = await _collections_dir(db)
    path = d / f"{collection_id}.yaml"
    if not path.exists():
        raise HTTPException(404, f"Collection '{collection_id}' not found")
    return {
        "collection_id": collection_id,
        "filename": path.name,
        "content": path.read_text(encoding="utf-8"),
    }


@router.post("/", status_code=201, summary="Create a new collection (admin)")
# Vytvori novy YAML soubor kolekce; overi slug nazev a validitu YAML; vyzaduje system_admin
async def create_collection(
    body: CollectionCreate,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    if not _SLUG_RE.match(body.filename):
        raise HTTPException(400, "Filename: only lowercase letters, digits, _ and - are allowed")
    try:
        data = yaml.safe_load(body.content)
    except yaml.YAMLError as exc:
        raise HTTPException(422, f"Invalid YAML: {exc}")
    if not isinstance(data, dict) or not data.get("id"):
        raise HTTPException(422, "Collection YAML must contain an 'id' field")
    d = await _collections_dir(db)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{body.filename}.yaml"
    if path.exists():
        raise HTTPException(409, f"Collection '{body.filename}' already exists")
    path.write_text(body.content, encoding="utf-8")
    return {"collection_id": body.filename, "filename": path.name}


@router.put("/{collection_id}", summary="Update collection YAML (admin)")
# Prepise YAML soubor kolekce novym obsahem; overi validitu YAML; vyzaduje system_admin
async def update_collection(
    collection_id: str,
    body: CollectionUpdate,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    d = await _collections_dir(db)
    path = d / f"{collection_id}.yaml"
    if not path.exists():
        raise HTTPException(404, f"Collection '{collection_id}' not found")
    try:
        yaml.safe_load(body.content)
    except yaml.YAMLError as exc:
        raise HTTPException(422, f"Invalid YAML: {exc}")
    path.write_text(body.content, encoding="utf-8")
    return {"collection_id": collection_id}


@router.delete("/{collection_id}", status_code=204, summary="Delete a collection (admin)")
# Smaze YAML soubor kolekce; vyzaduje roli system_admin
async def delete_collection(
    collection_id: str,
    current_user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    d = await _collections_dir(db)
    path = d / f"{collection_id}.yaml"
    if not path.exists():
        raise HTTPException(404, f"Collection '{collection_id}' not found")
    path.unlink()
