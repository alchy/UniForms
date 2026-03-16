from abc import ABC, abstractmethod
from typing import Optional

from app.models.user import User

# ---------------------------------------------------------------------------
# Abstraktní rozhraní autentizačního provideru.
# Definuje kontrakt pro metody authenticate() a get_user().
# Konkrétní implementace: SimpleAuthProvider (SQLite), LDAPProvider (stub),
# OAuthProvider (stub). Přepnutí provideru se provádí v .env (AUTH_PROVIDER).
# ---------------------------------------------------------------------------

class AuthProvider(ABC):
    """
    Rozhraní pro autentizační provider.

    Konkrétní implementace:
      - SimpleAuthProvider  (app/auth/simple_auth.py)  – username/password z .env
      - OAuthProvider       (app/auth/oauth_auth.py)   – stub pro OAuth2
      - LDAPProvider        (app/auth/ldap_auth.py)    – stub pro LDAP/AD

    Přepnutí: změň AUTH_PROVIDER v .env (nebo app/config.py).
    API tohoto rozhraní se nemění – pouze se swapuje implementace.
    """

    @abstractmethod
    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Ověří přihlašovací údaje.
        Vrátí User při úspěchu, None při nesprávných údajích.
        """
        ...

    @abstractmethod
    async def get_user(self, username: str) -> Optional[User]:
        """
        Načte uživatele dle username.
        Vrátí User nebo None pokud uživatel neexistuje nebo není aktivní.
        """
        ...
