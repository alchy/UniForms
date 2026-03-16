from typing import Optional

from app.auth.auth_provider import AuthProvider
from app.models.user import User

# ---------------------------------------------------------------------------
# LDAP / Active Directory autentizační provider – stub pro budoucí implementaci.
# Aktivace: AUTH_PROVIDER=ldap v .env. Metody authenticate() a get_user()
# je nutné doplnit (např. pomocí knihovny ldap3).
# ---------------------------------------------------------------------------

class LDAPProvider(AuthProvider):
    """
    LDAP / Active Directory autentizační provider – stub pro budoucí implementaci.

    Aktivace: nastav AUTH_PROVIDER=ldap v .env
    a doplň implementaci metod authenticate() a get_user().
    """

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        raise NotImplementedError("LDAPProvider: implementace zatím není dokončena")

    async def get_user(self, username: str) -> Optional[User]:
        raise NotImplementedError("LDAPProvider: implementace zatím není dokončena")
