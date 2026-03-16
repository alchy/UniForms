from typing import Optional

from app.auth.auth_provider import AuthProvider
from app.models.user import User

# ---------------------------------------------------------------------------
# OAuth2 autentizační provider – stub pro budoucí implementaci.
# Aktivace: AUTH_PROVIDER=oauth v .env. Metody authenticate() a get_user()
# je nutné doplnit dle konkrétního OAuth2 poskytovatele (Azure AD, Google, …).
# ---------------------------------------------------------------------------

class OAuthProvider(AuthProvider):
    """
    OAuth2 autentizační provider – stub pro budoucí implementaci.

    Aktivace: nastav AUTH_PROVIDER=oauth v .env
    a doplň implementaci metod authenticate() a get_user().
    """

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        raise NotImplementedError("OAuthProvider: implementace zatím není dokončena")

    async def get_user(self, username: str) -> Optional[User]:
        raise NotImplementedError("OAuthProvider: implementace zatím není dokončena")
