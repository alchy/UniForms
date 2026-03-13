from pathlib import Path

import aiosqlite
from fastapi import Depends

from app.config import settings
from app.core.database import get_db
from app.services.settings_service import get_setting
from app.storage.base import StorageBackend
from app.storage.file_backend import FileStorageBackend


async def get_storage(
    collection_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> StorageBackend:
    """
    FastAPI dependency – returns a StorageBackend scoped to the given collection.
    FastAPI automatically resolves `collection_id` from the URL path parameter.
    """
    records_dir = Path(
        await get_setting(db, "records_dir") or settings.default_records_dir
    )
    return FileStorageBackend(records_dir / collection_id)
