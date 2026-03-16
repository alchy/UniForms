from collections.abc import AsyncGenerator
from pathlib import Path

import aiosqlite

from app.config import settings
from app.core.security import hash_password

# ---------------------------------------------------------------------------
# Správa SQLite databáze.
# Zajišťuje inicializaci schématu (tabulky users, settings, collection_roles),
# seed prvního admin uživatele, migrace starých názvů rolí a FastAPI dependency
# get_db(), která otevírá a zavírá spojení pro každý request.
# ---------------------------------------------------------------------------

# FastAPI dependency – poskytne DB spojeni pro jeden request a po skonceni ho uzavre
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        yield db


# Inicializuje SQLite databazi pri startu aplikace: vytvori tabulky, zaseeduje admina a vychozi nastaveni
async def init_db() -> None:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row

        # Vytvori tabulky users, settings a collection_roles, pokud neexistuji
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                username         TEXT    UNIQUE NOT NULL,
                hashed_password  TEXT    NOT NULL,
                role             TEXT    NOT NULL DEFAULT 'system_reader',
                is_active        INTEGER NOT NULL DEFAULT 1,
                created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collection_roles (
                username      TEXT NOT NULL,
                collection_id TEXT NOT NULL,
                role          TEXT NOT NULL,
                PRIMARY KEY (username, collection_id)
            );
        """)

        # Vychozi nastaveni cest; INSERT OR IGNORE = zapise se jen pri prvnim spusteni
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('records_dir', ?)",
            (settings.default_records_dir,),
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('schemas_dir', ?)",
            (settings.default_schemas_dir,),
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('collections_dir', ?)",
            (settings.default_collections_dir,),
        )

        # Migrace starsich nazvu systemovych roli na aktualni (system_admin, system_reader)
        await db.execute("UPDATE users SET role = 'system_admin' WHERE role = 'admin'")
        await db.execute("UPDATE users SET role = 'system_reader' WHERE role = 'analyst'")
        # Migrace starsich nazvu collection roli na aktualni (collection_admin, collection_user)
        await db.execute("UPDATE collection_roles SET role = 'collection_admin' WHERE role = 'admin'")
        await db.execute("UPDATE collection_roles SET role = 'collection_user' WHERE role = 'user'")

        # Seed prvniho admin uzivatele; provede se jen kdyz je tabulka users prazdna
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            user_count = row[0]

        if user_count == 0:
            await db.execute(
                "INSERT INTO users (username, hashed_password, role, is_active) VALUES (?, ?, 'system_admin', 1)",
                (settings.admin_username, hash_password(settings.admin_password)),
            )

        await db.commit()
