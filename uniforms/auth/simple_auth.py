import secrets
from typing import Optional

import aiosqlite

from uniforms.auth.access_manager_auth import AUTH_SOURCE_AM, OtpResult, auth_provider, is_configured, verify_otp
from uniforms.auth.auth_provider import AuthProvider
from uniforms.core.security import hash_password, verify_password
from uniforms.models.user import User

# ---------------------------------------------------------------------------
# Výchozí autentizační provider nad SQLite tabulkou users.
#
# Každý účet má zdroj ověření (users.auth_source):
#   local          – bcrypt heslo v lokální DB, role z lokální DB
#   access_manager – OTP kód ověří access-manager; ROLI určují skupiny realmu
#                    (admin → system_admin, user → system_reader, jinak bez přístupu)
#                    a při každém přihlášení se propíše do lokální DB
# Je-li access-manager nakonfigurovaný, člen skupiny user/admin realmu dostane
# lokální účet při prvním OTP přihlášení sám (lokální účty dál heslem).
# AUTH_PROVIDER=access_manager: přes access-manager jde KAŽDÉ přihlášení,
# i účtů s auth_source=local (lokální hesla se nepoužijí).
# Aktivitu (is_active) dál drží lokální DB – deaktivovaný účet neprojde.
# ---------------------------------------------------------------------------


class SimpleAuthProvider(AuthProvider):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        # Details of the last attempt for the audit trail (never the secret)
        self.last_method: Optional[str] = None
        self.last_otp: Optional[OtpResult] = None
        self.last_denied: Optional[str] = None   # UniForms-side refusal reason

    async def _row(self, username: str):
        async with self.db.execute(
            "SELECT username, hashed_password, role, is_active, auth_source"
            " FROM users WHERE username = ?",
            (username,),
        ) as cursor:
            return await cursor.fetchone()

    async def _otp_login(self, username: str, code: str, client_origin, row) -> Optional[User]:
        self.last_method = AUTH_SOURCE_AM
        self.last_otp = await verify_otp(username, code, client_origin)
        if not self.last_otp.ok:
            return None
        role = self.last_otp.role()
        if role is None:
            self.last_denied = "not_in_access_group"
            return None
        if row is None:
            await self.db.execute(
                "INSERT INTO users (username, hashed_password, role, auth_source) VALUES (?, ?, ?, ?)",
                (username, await hash_password(secrets.token_urlsafe(32)), role, AUTH_SOURCE_AM),
            )
        elif row["role"] != role:
            await self.db.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
        await self.db.commit()
        return User(username=username, role=role)

    async def authenticate(
        self, username: str, password: str, client_origin: Optional[str] = None
    ) -> Optional[User]:
        row = await self._row(username)
        global_am = auth_provider() == "access_manager"

        if row is None:
            # Unknown locally: a member of the realm's user/admin group gets an
            # account on first OTP login (whenever access-manager is configured)
            if global_am or is_configured():
                return await self._otp_login(username, password, client_origin, None)
            return None
        if not row["is_active"]:
            self.last_denied = "inactive"
            return None
        if global_am or row["auth_source"] == AUTH_SOURCE_AM:
            return await self._otp_login(username, password, client_origin, row)

        self.last_method = "local"
        if not await verify_password(password, row["hashed_password"]):
            return None
        return User(username=row["username"], role=row["role"])

    async def get_user(self, username: str) -> Optional[User]:
        row = await self._row(username)
        if not row or not row["is_active"]:
            return None
        return User(username=row["username"], role=row["role"])
