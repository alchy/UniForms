from typing import Optional

import aiosqlite

from app.auth.auth_provider import AuthProvider
from app.core.security import verify_password
from app.models.user import User


class SimpleAuthProvider(AuthProvider):
    """
    Autentizační provider čtoucí uživatele z SQLite databáze.
    Admin uživatel je vytvořen při startu aplikace (init_db).
    Správa uživatelů je dostupná v admin GUI.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        async with self.db.execute(
            "SELECT username, hashed_password, role, is_active FROM users WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row or not row["is_active"]:
            return None
        if not verify_password(password, row["hashed_password"]):
            return None
        return User(username=row["username"], role=row["role"])

    async def get_user(self, username: str) -> Optional[User]:
        async with self.db.execute(
            "SELECT username, role, is_active FROM users WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row or not row["is_active"]:
            return None
        return User(username=row["username"], role=row["role"])
