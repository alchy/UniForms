# Authentication and Configuration

This document describes how UniForms handles login, stores passwords, issues tokens, and verifies every protected request. Intended for: developers extending the backend, administrators deploying the application, security auditors.

---

## Overview

Authentication ensures that only authorized users access records and configuration. The implementation rests on three pillars:

- **Configuration** – `pydantic-settings` reads the `.env` file at startup and exposes a `Settings` singleton available throughout the application.
- **Password storage** – passwords are never stored in plaintext; bcrypt is used.
- **Session** – after successful login the backend issues a JWT as an httpOnly cookie. Token validity is verified on every protected request.

---

## How it works

```
Browser: POST /api/v1/auth/login  { username, password }
    │
    ▼
SimpleAuthProvider.authenticate()
    │  loads row from SQLite users table
    │  checks is_active
    │  bcrypt.checkpw(password, hashed_password)
    │
    ├─ failure → asyncio.sleep(1) → HTTP 401
    │
    ▼
create_access_token({"sub": username, "role": role})
    │  HS256, signed with JWT_SECRET_KEY
    │  claim exp = now + JWT_EXPIRE_MINUTES
    ▼
Set-Cookie: uniforms_token=<JWT>; HttpOnly; SameSite=Lax; Max-Age=<seconds>
    │
    ▼
Every protected request:
    │  require_auth reads cookie uniforms_token
    │  decode_token: verifies signature + exp
    │  returns User object as FastAPI Depends
    ▼
require_admin: checks role == "system_admin", otherwise HTTP 403
```

---

## Quick start – login and first protected request

```bash
# 1. Login — cookie saved to cookie-jar
curl -c cookies.txt -X POST http://localhost:8080/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "admin"}'

# 2. Use cookie — protected endpoint
curl -b cookies.txt http://localhost:8080/api/v1/records/soc/
```

The first command returns HTTP 200 with `{"access_token": "...", "token_type": "bearer"}` and sets the cookie `uniforms_token`. The second command returns the list of records in the `soc` collection.

> **Note:** The default password `admin/admin` is only for the first run. Before production deployment change `ADMIN_PASSWORD` in `.env` **and** delete (or clear) the SQLite database so the new hash is seeded. See the [Admin seeding](#admin-seeding) section.

---

## Step by step – what happens at login

### 1. Sending credentials

The browser sends an HTTP POST with a JSON body:

```json
{ "username": "user1", "password": "my-password" }
```

Data travels **exclusively over an encrypted channel (HTTPS)**. Uvicorn listens on HTTP by default — deploying behind a reverse proxy (nginx, Caddy) with TLS is mandatory for production.

The login form at `/login` assembles this body with JavaScript and sends it via a `fetch()` call. The password never leaves the browser as part of a URL or query parameter.

### 2. Password verification (bcrypt)

`SimpleAuthProvider.authenticate()` in `app/auth/simple_auth.py`:

1. Loads the `users` row from SQLite by `username`.
2. Checks `is_active == 1` — a deactivated account gets HTTP 401.
3. Calls `verify_password(plain, hashed)` from `app/core/security.py`:

```python
def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())
```

bcrypt comparison is intentionally slow (cost factor ≈ 12 rounds). An attacker with a stolen database needs significantly more time to crack hashes than with MD5 or SHA.

### 3. JWT issuance

After successful verification `auth.py` calls `create_access_token()`:

```python
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
```

Call at login (`auth.py`):

```python
token = create_access_token({"sub": user.username, "role": user.role})
```

The token is signed with algorithm **HS256** using `JWT_SECRET_KEY`. It contains three claims:

| Claim | Content |
|-------|---------|
| `sub` | Username of the logged-in user |
| `role` | `"system_admin"` or `"system_reader"` |
| `exp` | Expiration Unix timestamp (UTC) |

### 4. Setting the cookie

The token is stored as an httpOnly cookie — JavaScript in the browser cannot access it, eliminating the risk of theft via XSS:

```python
response.set_cookie(
    key="uniforms_token",
    value=token,
    httponly=True,
    samesite="lax",
    max_age=settings.jwt_expire_minutes * 60,  # seconds
)
```

| Attribute | Value | Reason |
|-----------|-------|--------|
| `httponly` | `True` | JavaScript cannot read the cookie |
| `samesite` | `"lax"` | Blocks CSRF on cross-site requests |
| `max_age` | `jwt_expire_minutes × 60` | Browser deletes cookie after expiry |

### 5. Cookie verification on every request

`require_auth` (FastAPI `Depends`) in `app/core/security.py` reads the cookie and calls `decode_token()`:

```python
def decode_token(token: str) -> TokenPayload:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    return TokenPayload(sub=payload["sub"], role=payload["role"])
```

PyJWT automatically verifies:
- **Signature** – whether the token was tampered with (HMAC-SHA256 with `JWT_SECRET_KEY`).
- **Expiration** – whether the current time has exceeded `exp`. If so, raises `ExpiredSignatureError`.

Every PyJWT exception is caught and returns HTTP 401 with no detailed error message — nothing that would help an attacker.

---

## Configuration via `.env`

`app/config.py` uses `pydantic-settings`. At module import the `.env` file is loaded **once** into the `Settings` singleton. Changes to `.env` at runtime have no effect — a server restart is required.

```
# .env – example production settings
JWT_SECRET_KEY=replace-with-strong-random-string-min-32-chars
JWT_EXPIRE_MINUTES=480
AUTH_PROVIDER=simple
ADMIN_USERNAME=admin
ADMIN_PASSWORD=secure-password
DATABASE_PATH=data/uniforms.db
```

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | `change-me-in-production-...` | JWT signing key – **must be changed** |
| `JWT_ALGORITHM` | `HS256` | Signing algorithm |
| `JWT_EXPIRE_MINUTES` | `480` (8 hours) | Token validity |
| `AUTH_PROVIDER` | `simple` | `simple` / `oauth` / `ldap` |
| `ADMIN_USERNAME` | `admin` | Seed admin username |
| `ADMIN_PASSWORD` | `admin` | Seed admin password (see below) |
| `DATABASE_PATH` | `data/uniforms.db` | Path to SQLite file |

---

## Admin seeding

`init_db()` in `app/core/database.py` runs at every application startup and creates the `users`, `settings`, and `collection_roles` tables if they don't exist. The admin account is seeded **only when the `users` table is completely empty**:

```python
count = await db.execute("SELECT COUNT(*) FROM users")
row = await count.fetchone()
if row[0] == 0:
    hashed = hash_password(settings.admin_password)
    await db.execute("INSERT INTO users ...", (settings.admin_username, hashed, "system_admin", 1))
```

The password from `.env` is **always** stored as a bcrypt hash — never in plaintext.

### Database migration

On startup `init_db()` also migrates any legacy role names to the current names:

- `admin` → `system_admin`
- `analyst` → `system_reader`
- collection role `admin` → `collection_admin`
- collection role `user` → `collection_user`

### What happens after changing `ADMIN_PASSWORD` in `.env`

The change affects the database **only on the first run with an empty DB**. If the `users` table already contains rows, seeding is skipped and the new password is not written to the DB.

Procedure for resetting the admin password in production:

```bash
# Option A – via API (recommended, no downtime)
curl -b cookies.txt -X PATCH http://localhost:8080/api/v1/users/admin \
     -H "Content-Type: application/json" \
     -d '{"password": "new-secure-password"}'

# Option B – delete DB (causes downtime, loses settings)
rm data/uniforms.db
# Set ADMIN_PASSWORD in .env, then restart the application
```

---

## Role model

### System roles (stored in JWT claim `role`)

| Role | Description |
|------|-------------|
| `system_admin` | Full access — manage users, settings, all collections, template editor, collection role management |
| `system_reader` | Can only access collections explicitly assigned in `collection_roles` |

### Collection roles (stored in DB table `collection_roles`)

| Role | Description |
|------|-------------|
| `collection_admin` | Can create/edit/delete templates and records; can edit the collection |
| `collection_user` | Can create and edit records; cannot delete records or edit templates |

`system_admin` bypasses all collection role checks.

---

## Security recommendations

### `JWT_SECRET_KEY`

The default key `"change-me-in-production-..."` is publicly known from the repository. An attacker with this key can sign any JWT and gain access to the application without a password.

Generate a strong key before first deployment:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Keep the key secret — never commit it to version control. `.env` is in `.gitignore`.

### Token validity (`JWT_EXPIRE_MINUTES`)

The default 480 minutes (8 hours) corresponds to the length of a work shift. After expiry the user must log in again. This can be reduced without code changes by editing `.env`.

On logout (`POST /api/v1/auth/logout`) the backend deletes the cookie — the token stops being sent. The token itself remains technically valid until `exp`. The application does not implement a token blacklist — if immediate revocation is needed, change `JWT_SECRET_KEY` (this invalidates **all** active sessions).

### Brute-force protection

On failed login the backend waits `asyncio.sleep(1)` before returning HTTP 401. A single thread can test at most ~60 passwords per minute. An attacker with parallel requests from one IP can bypass this — for production deployments exposed to the network consider adding a per-IP rate limiter (e.g. `slowapi`).

### User deactivation

`is_active = 0` in the `users` table blocks login immediately, but does not revoke existing cookies issued before deactivation. Again: for immediate revocation, change `JWT_SECRET_KEY`.

### HTTPS

Without TLS the cookie travels over the network in plaintext and can be intercepted (man-in-the-middle). The `Secure` attribute is not set on the cookie — we recommend adding it after deploying behind an HTTPS proxy.

---

## Function and class reference

| Identifier | File | Description |
|---|---|---|
| `Settings` | `app/config.py` | pydantic-settings singleton; loaded from `.env` at import |
| `hash_password(plain)` | `app/core/security.py` | bcrypt hash of password |
| `verify_password(plain, hashed)` | `app/core/security.py` | bcrypt comparison |
| `create_access_token(data, expires_delta)` | `app/core/security.py` | issues HS256 JWT with `exp`; `data` = `{"sub": username, "role": role}` |
| `decode_token(token)` | `app/core/security.py` | verifies signature + exp, returns `TokenPayload` |
| `require_auth` | `app/core/security.py` | FastAPI Depends – reads cookie, returns `User` or HTTP 401 |
| `require_admin` | `app/core/security.py` | FastAPI Depends – builds on `require_auth`, HTTP 403 if role != system_admin |
| `require_collection_access` | `app/core/collection_deps.py` | FastAPI Depends – allows system_admin or any collection role |
| `require_collection_admin` | `app/core/collection_deps.py` | FastAPI Depends – allows system_admin or collection_admin role |
| `SimpleAuthProvider.authenticate()` | `app/auth/simple_auth.py` | DB lookup + bcrypt verification |
| `init_db()` | `app/core/database.py` | creates tables, seeds admin and path settings, migrates legacy roles |
| `POST /api/v1/auth/login` | `app/api/v1/auth.py` | accepts credentials, returns token + sets cookie |
| `POST /api/v1/auth/logout` | `app/api/v1/auth.py` | deletes cookie |
| `GET /api/v1/auth/me` | `app/api/v1/auth.py` | returns logged-in user profile |
