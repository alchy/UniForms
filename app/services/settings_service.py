from typing import Optional

import aiosqlite

# ---------------------------------------------------------------------------
# Služba pro čtení a zápis runtime nastavení uložených v SQLite tabulce settings.
# Klíče: records_dir, schemas_dir, collections_dir (editovatelné za běhu přes GUI).
# Ostatní nastavení (JWT, hesla, cesty) jsou v .env a vyžadují restart.
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
