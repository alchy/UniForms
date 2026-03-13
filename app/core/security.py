from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Cookie, Depends, HTTPException, status

from app.config import settings
from app.models.user import TokenPayload, User

COOKIE_NAME = "uniforms_token"


# ---------------------------------------------------------------------------
# Vyjimky pro webove routy (presmerovani misto JSON chyby)
# ---------------------------------------------------------------------------

class WebLoginRequired(Exception):
    """Uzivatel neni prihlasen – presmerovani na /login."""


class WebAdminRequired(Exception):
    """Uzivatel nema roli system_admin – presmerovani na /dashboard."""


# ---------------------------------------------------------------------------
# Hesla (bcrypt)
# ---------------------------------------------------------------------------

# Vrati bcrypt hash hesla v plaintextu
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


# Overi shodu plaintextoveho hesla s bcrypt hashem
def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

# Vytvori HS256 JWT s claimy sub, role a exp; platnost dle JWT_EXPIRE_MINUTES
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# Dekoduje a overi JWT; vyhodi vyjimku PyJWT pri neplatnem tokenu nebo expiraci
def decode_token(token: str) -> TokenPayload:
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    return TokenPayload(**payload)


# ---------------------------------------------------------------------------
# FastAPI dependencies – ochrana API endpointu
# ---------------------------------------------------------------------------

# Vyzaduje platny JWT cookie; vrati objekt User nebo HTTP 401
async def require_auth(
    uniforms_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    if not uniforms_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated – missing token",
        )
    try:
        payload = decode_token(uniforms_token)
        return User(username=payload.sub, role=payload.role)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired – please log in again",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )


# Vyzaduje roli system_admin; jinak HTTP 403
async def require_admin(current_user: User = Depends(require_auth)) -> User:
    if current_user.role != "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied – admin role required",
        )
    return current_user
