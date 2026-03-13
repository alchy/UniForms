import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.record import UniRecord
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class FileStorageBackend(StorageBackend):
    """
    StorageBackend implementation storing records as JSON files.

    Records: {records_dir}/{record_id}.json
    Locks:   {records_dir}/{record_id}.lock
    """

    def __init__(self, records_dir: Path) -> None:
        self.records_dir = records_dir
        records_dir.mkdir(parents=True, exist_ok=True)

    def _record_path(self, record_id: str) -> Path:
        return self.records_dir / f"{record_id}.json"

    def _lock_path(self, record_id: str) -> Path:
        return self.records_dir / f"{record_id}.lock"

    def _load_record_from_path(self, path: Path) -> Optional[UniRecord]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            record = UniRecord(**data)
            lock_path = self._lock_path(record.record_id)
            if lock_path.exists():
                try:
                    lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
                    record.locked_by = lock_data.get("locked_by")
                except Exception:
                    pass
            return record
        except Exception as exc:
            logger.warning("Cannot load record '%s': %s", path.name, exc)
            return None

    async def list_records(self) -> list[UniRecord]:
        records = []
        json_files = sorted(
            [p for p in self.records_dir.glob("*.json") if not p.name.endswith(".lock")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for json_file in json_files:
            record = self._load_record_from_path(json_file)
            if record:
                records.append(record)
        return records

    async def get_record(self, record_id: str) -> Optional[UniRecord]:
        path = self._record_path(record_id)
        if not path.exists():
            return None
        return self._load_record_from_path(path)

    async def save_record(self, record: UniRecord) -> None:
        path = self._record_path(record.record_id)
        data = record.model_dump(mode="json", exclude={"locked_by"})
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    async def delete_record(self, record_id: str) -> bool:
        path = self._record_path(record_id)
        if not path.exists():
            return False
        path.unlink()
        lock_path = self._lock_path(record_id)
        if lock_path.exists():
            lock_path.unlink()
        return True

    async def acquire_lock(self, record_id: str, username: str) -> bool:
        lock_path = self._lock_path(record_id)
        if lock_path.exists():
            try:
                existing = json.loads(lock_path.read_text(encoding="utf-8"))
                if existing.get("locked_by") == username:
                    # Refresh lock timestamp
                    lock_data = {
                        "locked_by": username,
                        "locked_at": datetime.now(timezone.utc).isoformat(),
                    }
                    lock_path.write_text(json.dumps(lock_data, ensure_ascii=False), encoding="utf-8")
                    return True
                else:
                    return False  # Locked by another user
            except Exception:
                return False  # Corrupt lock file – treat as locked

        lock_data = {
            "locked_by": username,
            "locked_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            lock_path.write_text(json.dumps(lock_data, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as exc:
            logger.warning("Cannot acquire lock for '%s': %s", record_id, exc)
            return False

    async def release_lock(self, record_id: str, username: str, force: bool = False) -> bool:
        lock_path = self._lock_path(record_id)
        if not lock_path.exists():
            return True
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
            if not force and existing.get("locked_by") != username:
                return False
            lock_path.unlink()
            return True
        except Exception as exc:
            logger.warning("Cannot release lock for '%s': %s", record_id, exc)
            return False

    async def get_lock_info(self, record_id: str) -> Optional[dict]:
        lock_path = self._lock_path(record_id)
        if not lock_path.exists():
            return None
        try:
            return json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            return None
