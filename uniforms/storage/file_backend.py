import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from uniforms.core.validation import is_safe_id
from uniforms.models.record import UniRecord
from uniforms.storage.base import StorageBackend

# ---------------------------------------------------------------------------
# Souborový storage backend ukládající záznamy jako JSON soubory.
# Každý záznam je uložen jako {records_dir}/{record_id}.json,
# zámek editace jako {records_dir}/{record_id}.lock.
# Operace jsou asynchronní; zámky jsou jednoduché soubory s metadaty.
# record_id se validuje na hranici backendu (ochrana proti path traversal).
# ---------------------------------------------------------------------------

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
        if not is_safe_id(record_id):
            raise ValueError(f"Unsafe record id: {record_id!r}")
        return self.records_dir / f"{record_id}.json"

    def _lock_path(self, record_id: str) -> Path:
        if not is_safe_id(record_id):
            raise ValueError(f"Unsafe record id: {record_id!r}")
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
            self.records_dir.glob("*.json"),
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

    async def record_exists(self, record_id: str) -> bool:
        return self._record_path(record_id).exists()

    async def save_record(self, record: UniRecord) -> None:
        path = self._record_path(record.record_id)
        data = record.model_dump(mode="json", exclude={"locked_by"})
        # Zapis pres docasny soubor + rename, aby pad uprostred zapisu neposkodil zaznam
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

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
        lock_json = json.dumps(
            {"locked_by": username, "locked_at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False,
        )
        try:
            # Exkluzivni vytvoreni souboru je atomicke – dva soubezne pozadavky
            # nemohou ziskat zamek oba (mode "x" selze, pokud soubor existuje)
            with lock_path.open("x", encoding="utf-8") as fh:
                fh.write(lock_json)
            return True
        except FileExistsError:
            pass
        except OSError as exc:
            logger.warning("Cannot acquire lock for '%s': %s", record_id, exc)
            return False

        # Zamek existuje – obnovime timestamp, jen pokud ho drzi stejny uzivatel
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
            if existing.get("locked_by") == username:
                lock_path.write_text(lock_json, encoding="utf-8")
                return True
            return False  # Locked by another user
        except Exception:
            return False  # Corrupt lock file – treat as locked

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
