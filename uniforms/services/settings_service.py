from pathlib import Path
from typing import Optional

import aiosqlite

from uniforms.config import settings

# ---------------------------------------------------------------------------
# Služba pro čtení a zápis runtime nastavení uložených v SQLite tabulce settings.
# Klíče: records_dir, schemas_dir, collections_dir (editovatelné za běhu přes GUI).
# Ostatní nastavení (JWT, hesla, cesty) jsou v .env a vyžadují restart.
# Helpery get_*_dir() jsou jediné místo, kde se runtime cesty rozhodují –
# hodnota z DB má přednost, jinak výchozí z konfigurace.
# ---------------------------------------------------------------------------

async def get_setting(db: aiosqlite.Connection, key: str) -> Optional[str]:
    """Vrátí hodnotu nastavení dle klíče nebo None."""
    async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


async def set_setting(db: aiosqlite.Connection, key: str, value: str) -> None:
    """Uloží nebo aktualizuje nastavení."""
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await db.commit()


async def get_all_settings(db: aiosqlite.Connection) -> dict[str, str]:
    """Vrátí všechna nastavení jako slovník."""
    async with db.execute("SELECT key, value FROM settings") as cursor:
        rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


async def _get_dir(db: aiosqlite.Connection, key: str, default: str) -> Path:
    return Path(await get_setting(db, key) or default)


async def get_records_dir(db: aiosqlite.Connection) -> Path:
    return await _get_dir(db, "records_dir", settings.default_records_dir)


async def get_schemas_dir(db: aiosqlite.Connection) -> Path:
    return await _get_dir(db, "schemas_dir", settings.default_schemas_dir)


async def get_collections_dir(db: aiosqlite.Connection) -> Path:
    return await _get_dir(db, "collections_dir", settings.default_collections_dir)
