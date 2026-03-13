from typing import Optional

from app.auth.auth_provider import AuthProvider
from app.models.user import User


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
