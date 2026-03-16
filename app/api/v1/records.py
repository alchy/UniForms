import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status

# ---------------------------------------------------------------------------
# API endpointy pro záznamy (records).
# GET    /records/{col}/           – seznam záznamů kolekce.
# POST   /records/{col}/           – vytvoření záznamu ze šablony.
# GET    /records/{col}/{id}        – detail záznamu.
# PATCH  /records/{col}/{id}        – aktualizace dat nebo stavu záznamu.
# DELETE /records/{col}/{id}        – smazání záznamu (vyžaduje system_admin nebo collection_admin).
# POST   /records/{col}/{id}/lock   – zamknutí záznamu pro editaci.
# DELETE /records/{col}/{id}/lock   – odemknutí záznamu.
# ---------------------------------------------------------------------------

from app.core.collection_deps import require_collection_access, require_collection_admin
from app.core.database import get_db
from app.models.collection import CollectionConfig
from app.models.record import CreateRecordRequest, UniRecord, UpdateRecordRequest
from app.models.user import User
from app.services import collection_service, record_service
from app.services.collection_service import get_accessible_collections
from app.services.settings_service import get_setting
from app.services.template_service import TemplateService, get_template_service
from app.storage import get_storage
from app.storage.base import StorageBackend
from app.config import settings
from pathlib import Path

router = APIRouter(prefix="/records/{collection_id}", tags=["Records"])


# Nacte konfiguraci kolekce z YAML souboru; vyhodi 404, pokud kolekce neexistuje
async def _get_collection(collection_id: str, db: aiosqlite.Connection) -> CollectionConfig:
    collections_dir = Path(
        await get_setting(db, "collections_dir") or settings.default_collections_dir
    )
    col = await collection_service.get_collection(collection_id, collections_dir)
    if not col:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found")
    return col


@router.get("/", response_model=list[UniRecord], summary="List records in collection")
# Vrati seznam vsech zaznamu v kolekci; vyzaduje pristup ke kolekci (collection_admin nebo collection_user)
async def list_records(
    current_user: User = Depends(require_collection_access),
    storage: StorageBackend = Depends(get_storage),
) -> list[UniRecord]:
    return await record_service.list_records(storage)


@router.post(
    "/",
    response_model=UniRecord,
    status_code=201,
    summary="Create a record from a template",
)
# Vytvori novy zaznam ze sablony; vyzaduje pristup ke kolekci
async def create_record(
    collection_id: str,
    request: CreateRecordRequest,
    current_user: User = Depends(require_collection_access),
    storage: StorageBackend = Depends(get_storage),
    svc: TemplateService = Depends(get_template_service),
    db: aiosqlite.Connection = Depends(get_db),
) -> UniRecord:
    template = await svc.get_template(request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{request.template_id}' not found")
    collection = await _get_collection(collection_id, db)
    return await record_service.create_record(
        storage, template, current_user.username, collection_id, collection
    )


@router.get("/{record_id}", response_model=UniRecord, summary="Get record")
# Vrati detail jednoho zaznamu; vyzaduje pristup ke kolekci
async def get_record(
    record_id: str,
    current_user: User = Depends(require_collection_access),
    storage: StorageBackend = Depends(get_storage),
) -> UniRecord:
    record = await record_service.get_record(storage, record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")
    return record


@router.patch("/{record_id}", response_model=UniRecord, summary="Update record")
# Aktualizuje stav a/nebo data zaznamu; vyzaduje pristup ke kolekci
async def update_record(
    record_id: str,
    request: UpdateRecordRequest,
    current_user: User = Depends(require_collection_access),
    storage: StorageBackend = Depends(get_storage),
) -> UniRecord:
    record = await record_service.update_record(storage, record_id, request)
    if not record:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")
    return record


@router.delete("/{record_id}", status_code=204, summary="Delete record (collection admin)")
# Smaze zaznam; vyzaduje roli collection_admin nebo system_admin
async def delete_record(
    record_id: str,
    current_user: User = Depends(require_collection_admin),
    storage: StorageBackend = Depends(get_storage),
) -> None:
    deleted = await record_service.delete_record(storage, record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")


# --- Zamky zaznamu ---

@router.post(
    "/{record_id}/lock",
    summary="Acquire record lock",
)
# Ziska zamek editace zaznamu; vraci 423, pokud zaznam zamkl jiny uzivatel
async def acquire_lock(
    record_id: str,
    current_user: User = Depends(require_collection_access),
    storage: StorageBackend = Depends(get_storage),
) -> dict:
    record = await storage.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")

    acquired = await storage.acquire_lock(record_id, current_user.username)
    if not acquired:
        lock_info = await storage.get_lock_info(record_id)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "message": "Record is locked by another user",
                "locked_by": lock_info.get("locked_by") if lock_info else None,
                "locked_at": lock_info.get("locked_at") if lock_info else None,
            },
        )
    return {"locked_by": current_user.username}


@router.delete("/{record_id}/lock", status_code=204, summary="Release record lock")
# Uvolni zamek zaznamu; system_admin muze uvolnit i cizi zamek
async def release_lock(
    record_id: str,
    current_user: User = Depends(require_collection_access),
    storage: StorageBackend = Depends(get_storage),
) -> None:
    force = current_user.role == "system_admin"
    await storage.release_lock(record_id, current_user.username, force=force)
