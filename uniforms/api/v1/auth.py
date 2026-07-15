import asyncio

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Response, status

# ---------------------------------------------------------------------------
# API endpointy pro autentizaci.
# POST /auth/login  – ověří přihlašovací údaje, vydá JWT cookie.
# POST /auth/logout – smaže JWT cookie.
# GET  /auth/me     – vrátí aktuálně přihlášeného uživatele.
# Vybírá a inicializuje správný AuthProvider dle nastavení AUTH_PROVIDER.
# ---------------------------------------------------------------------------

from uniforms.auth.auth_provider import AuthProvider
from uniforms.auth.ldap_auth import LDAPProvider
from uniforms.auth.oauth_auth import OAuthProvider
from uniforms.auth.simple_auth import SimpleAuthProvider
from uniforms.config import settings
from uniforms.core.database import get_db
from uniforms.core.security import COOKIE_NAME, create_access_token, require_auth
from uniforms.models.user import LoginRequest, Token, User

router = APIRouter(prefix="/auth", tags=["Autentizace"])


# Vrati instanci auth providera dle nastaveni AUTH_PROVIDER v .env
async def get_auth_provider(
    db: aiosqlite.Connection = Depends(get_db),
) -> AuthProvider:
    if settings.auth_provider == "oauth":
        return OAuthProvider()
    if settings.auth_provider == "ldap":
        return LDAPProvider()
    return SimpleAuthProvider(db)


@router.post(
    "/login",
    response_model=Token,
    summary="Přihlášení uživatele",
    description="Ověří přihlašovací údaje a vrátí JWT token nastavený jako httpOnly cookie.",
)
# Overi prihlasovaci udaje a nastavi JWT httpOnly cookie; JWT obsahuje sub (username) a role (system role)
async def login(
    credentials: LoginRequest,
    response: Response,
    provider: AuthProvider = Depends(get_auth_provider),
) -> Token:
    user = await provider.authenticate(credentials.username, credentials.password)

    if not user:
        # Zpomaleni odpovedi pri neuspesnem prihlaseni (ochrana proti brute-force)
        await asyncio.sleep(1)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávné přihlašovací údaje",
        )

    # JWT obsahuje sub=username a role=system_role (system_admin nebo system_reader)
    token = create_access_token({"sub": user.username, "role": user.role})

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,  # v produkci za HTTPS nastav COOKIE_SECURE=true
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )

    return Token(access_token=token)


@router.post(
    "/logout",
    summary="Odhlášení uživatele",
)
# Smaze JWT cookie a odhlas uzivatele
async def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME)
    return {"detail": "Odhlášení proběhlo úspěšně"}


@router.get(
    "/me",
    response_model=User,
    summary="Informace o přihlášeném uživateli",
)
# Vrati profil aktualne prihlaseneho uzivatele ze JWT cookie
async def get_me(current_user: User = Depends(require_auth)) -> User:
    return current_user
