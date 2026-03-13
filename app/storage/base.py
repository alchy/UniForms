from abc import ABC, abstractmethod
from typing import Optional

from app.models.record import UniRecord


class StorageBackend(ABC):
    """
    Abstract interface for record storage.
    Implementations: FileStorageBackend (JSON files), future Elasticsearch, MongoDB, …
    Templates are read-only and managed separately by TemplateService.
    """

    @abstractmethod
    async def list_records(self) -> list[UniRecord]:
        """Return all records sorted newest first."""

    @abstractmethod
    async def get_record(self, record_id: str) -> Optional[UniRecord]:
        """Return a record by record_id or None."""

    @abstractmethod
    async def save_record(self, record: UniRecord) -> None:
        """Save a record (create or update)."""

    @abstractmethod
    async def delete_record(self, record_id: str) -> bool:
        """Delete a record. Returns True if it existed."""

    @abstractmethod
    async def acquire_lock(self, record_id: str, username: str) -> bool:
        """
        Try to acquire a lock for the record.
        Returns True if lock acquired or already owned by the same user.
        Returns False if locked by another user.
        """

    @abstractmethod
    async def release_lock(self, record_id: str, username: str, force: bool = False) -> bool:
        """
        Release a record lock.
        force=True allows releasing regardless of owner (admin use).
        Returns True if released or lock did not exist.
        """

    @abstractmethod
    async def get_lock_info(self, record_id: str) -> Optional[dict]:
        """Return lock info {locked_by, locked_at} or None if not locked."""
