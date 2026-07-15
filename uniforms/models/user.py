from pydantic import BaseModel, Field
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Pydantic modely pro uživatele a autentizaci.
# User a TokenPayload se používají interně při ověřování JWT.
# LoginRequest, Token, UserCreate, UserResponse, UserUpdate obsluhují
# příslušné API endpointy pro přihlášení a správu uživatelů.
# Role jsou omezené Literal typy – API odmítne neznámou roli (422).
# ---------------------------------------------------------------------------

SystemRole = Literal["system_admin", "system_reader"]
CollectionRoleId = Literal["collection_admin", "collection_user"]

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
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


# --- Modely pro správu uživatelů ---

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)
    role: SystemRole = "system_reader"


class UserUpdate(BaseModel):
    role: Optional[SystemRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=1, max_length=256)
