from pydantic import BaseModel
from typing import Optional

# ---------------------------------------------------------------------------
# Pydantic modely pro uživatele a autentizaci.
# User a TokenPayload se používají interně při ověřování JWT.
# LoginRequest, Token, UserCreate, UserResponse, UserUpdate obsluhují
# příslušné API endpointy pro přihlášení a správu uživatelů.
# ---------------------------------------------------------------------------

class User(BaseModel):
    username: str
    role: str = "system_reader"
    is_active: bool = True


class TokenPayload(BaseModel):
    sub: str       # username
    role: str = "system_reader"
    exp: Optional[int] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


# --- Modely pro správu uživatelů ---

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "system_reader"


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
