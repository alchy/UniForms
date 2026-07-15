import aiosqlite
from fastapi import Depends

from uniforms.core.database import get_db
from uniforms.core.validation import require_slug
from uniforms.services.settings_service import get_records_dir
from uniforms.storage.base import StorageBackend
from uniforms.storage.file_backend import FileStorageBackend


async def get_storage(
    collection_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> StorageBackend:
    """
    FastAPI dependency – returns a StorageBackend scoped to the given collection.
    FastAPI automatically resolves `collection_id` from the URL path parameter.
    """
    require_slug(collection_id, "collection_id")
    records_dir = await get_records_dir(db)
    return FileStorageBackend(records_dir / collection_id)
