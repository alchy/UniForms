# Autentizace a autorizace v UniForms

Přístup do UniForms je chráněn třemi pilíři:

1. **Konfigurace v `.env`** — JWT secret, doba platnosti tokenu, volba auth provideru a init admin účet.
2. **Úložiště hesel** — hesla jsou hashována algoritmem bcrypt; plain text se nikde neukládá.
3. **Session přes JWT cookie** — po přihlášení dostane prohlížeč httpOnly cookie `uniforms_token`; ta se posílá automaticky s každým dalším requestem.

---

## 1. Přihlašovací tok

```
Prohlížeč                      FastAPI /api/v1/auth/login
   |                                     |
   |-- POST {username, password} ------> |
   |                                     |-- ověř auth provider (simple/ldap/oauth)
   |                                     |       |
   |                                     |       +-- chyba --> sleep(1) --> HTTP 401
   |                                     |
   |                                     |-- bcrypt.verify(password, hashed_password)
   |                                     |       |
   |                                     |       +-- neplatné --> sleep(1) --> HTTP 401
   |                                     |
   |                                     |-- vytvoř JWT
   |                                     |   { sub: username, role: system_role, exp: now+JWT_EXPIRE_MINUTES }
   |                                     |   podpis: HS256 + JWT_SECRET_KEY
   |                                     |
   |<-- Set-Cookie: uniforms_token=<JWT> |
   |    (httpOnly, samesite=lax)         |
   |                                     |
   |-- GET /api/v1/... ---------------> |
   |   Cookie: uniforms_token=<JWT>      |-- decode_token() → TokenPayload
   |                                     |-- require_auth() / require_admin()
   |<-- 200 OK / 401 / 403 ------------ |
```

`sleep(1)` při chybném přihlášení zpomaluje brute-force útoky bez nutnosti blokovat IP.

---

## 2. Konfigurační klíče v `.env`

| Klíč | ✓ | Výchozí | Popis |
|------|---|---------|-------|
| `JWT_SECRET_KEY` | ✓ | `change-me-in-production` | Podepisovací klíč JWT. Nastavte silný náhodný řetězec (min. 32 znaků). |
| `JWT_EXPIRE_MINUTES` | | `480` | Platnost tokenu v minutách (výchozí 8 hodin). Po vypršení je nutné se znovu přihlásit. |
| `JWT_ALGORITHM` | | `HS256` | Algoritmus podpisu JWT. Výchozí `HS256` je dostačující pro interní nasazení. |
| `AUTH_PROVIDER` | | `simple` | Způsob ověření identity: `simple`, `ldap`, nebo `oauth`. |
| `ADMIN_USERNAME` | | `admin` | Uživatelské jméno init admin účtu vytvořeného při prvním startu. |
| `ADMIN_PASSWORD` | | `admin` | Heslo init admin účtu. **Okamžitě změňte po prvním spuštění.** |
| `DATABASE_PATH` | | `data/uniforms.db` | Cesta k SQLite databázi s uživateli a collection rolemi. |

> **Pozor:** Nikdy necommitujte `.env` soubor do verzovacího systému. Výchozí `JWT_SECRET_KEY` a `ADMIN_PASSWORD` jsou pouze pro lokální vývoj.

Generování silného klíče:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 3. Auth providery

UniForms podporuje tři způsoby ověření identity, volba se provádí klíčem `AUTH_PROVIDER` v `.env`.

### `simple` — lokální databáze (výchozí)

Hesla jsou uložena jako bcrypt hash v SQLite databázi. Vhodné pro malé týmy a interní nástroje bez LDAP/SSO infrastruktury.

```ini
AUTH_PROVIDER=simple
```

### `ldap` — podnikový adresář

Ověření probíhá bind operací na LDAP/Active Directory serveru. Hesla se v UniForms vůbec neukládají. Vhodné pro organizace s centrálním AD.

```ini
AUTH_PROVIDER=ldap
LDAP_SERVER=ldap://dc.example.com
LDAP_BASE_DN=DC=example,DC=com
```

> **Poznámka:** I při LDAP provideru jsou systémové a collection role uloženy v SQLite — LDAP slouží pouze k ověření hesla.

### `oauth` — externího poskytovatele (SSO)

Přihlášení přes OAuth 2.0 / OIDC (např. Google, GitHub, Azure AD). Po úspěšném OAuth flow UniForms vydá vlastní JWT cookie. Vhodné pro SaaS nasazení nebo organizace s existujícím SSO.

```ini
AUTH_PROVIDER=oauth
OAUTH_CLIENT_ID=<client_id>
OAUTH_CLIENT_SECRET=<client_secret>
OAUTH_DISCOVERY_URL=https://accounts.google.com/.well-known/openid-configuration
```

---

## 4. Rolový systém

Přístupová práva jsou dvouvrstvá: **systémová role** (v JWT, platí globálně) + **collection role** (v SQLite, platí pro konkrétní kolekci).

### 4.1 Systémové role

Systémová role se ukládá do JWT claimu `role` při přihlášení.

| Role | Popis |
|------|-------|
| `system_admin` | Plný přístup ke všemu: API, správa uživatelů, nastavení, všechny kolekce bez omezení. |
| `system_reader` | Může se přihlásit a přistupovat ke kolekcím dle přiřazených collection rolí. Bez collection role nemá přístup k žádné kolekci. |

### 4.2 Collection role

Collection role je přiřazena konkrétnímu uživateli pro konkrétní kolekci. Uložena v tabulce `collection_roles` v SQLite.

| Role | Popis |
|------|-------|
| `collection_admin` | Správa šablon v kolekci, mazání záznamů, vše co `collection_user`. |
| `collection_user` | Čtení a tvorba/editace záznamů v kolekci. |

### 4.3 Matice přístupu

| Akce | system_admin | system_reader + collection_admin | system_reader + collection_user | system_reader bez role |
|------|:---:|:---:|:---:|:---:|
| Zobrazit záznamy kolekce | ✓ | ✓ | ✓ | ✗ |
| Vytvořit / editovat záznam | ✓ | ✓ | ✓ | ✗ |
| Smazat záznam | ✓ | ✓ | ✗ | ✗ |
| Spravovat šablony kolekce | ✓ | ✓ | ✗ | ✗ |
| Spravovat uživatele (globálně) | ✓ | ✗ | ✗ | ✗ |
| Spravovat nastavení aplikace | ✓ | ✗ | ✗ | ✗ |

> **Tip:** `system_admin` obchází kontrolu collection rolí úplně — `require_collection_access` i `require_collection_admin` mu vždy projdou.

---

## 5. Správa uživatelů

Uživatelé se spravují přes REST API. Všechny níže uvedené operace vyžadují `system_admin`.

### Přihlášení (kompletní příklad)

```bash
# Přihlášení — cookie se uloží do souboru cookies.txt
curl -s -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'

# Ověření — kdo jsem?
curl -s -b cookies.txt http://localhost:8000/api/v1/auth/me

# Odhlášení
curl -s -b cookies.txt -c cookies.txt -X POST http://localhost:8000/api/v1/auth/logout
```

Úspěšná odpověď `/auth/me`:

```json
{
  "username": "admin",
  "role": "system_admin",
  "is_active": true
}
```

### Vytvoření nového uživatele

```bash
curl -s -b cookies.txt -X POST http://localhost:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{
    "username": "jana.novak",
    "password": "bezpecne-heslo-123",
    "role": "system_reader"
  }'
```

### Přiřazení collection role

```bash
# Přiřadit uživateli jana.novak roli collection_user v kolekci "incidenty"
curl -s -b cookies.txt -X POST http://localhost:8000/api/v1/users/jana.novak/collection-roles \
  -H "Content-Type: application/json" \
  -d '{
    "collection_id": "incidenty",
    "role": "collection_user"
  }'
```

### Odebrání collection role

```bash
curl -s -b cookies.txt -X DELETE \
  "http://localhost:8000/api/v1/users/jana.novak/collection-roles/incidenty"
```

### Výpis uživatelů

```bash
curl -s -b cookies.txt http://localhost:8000/api/v1/users
```

---

## 6. Bezpečnostní doporučení

**JWT_SECRET_KEY**
Nastavte minimálně 32 náhodných znaků. Při kompromitaci klíče jsou všechny aktivní session okamžitě neplatné po jeho změně.

**Výchozí admin heslo**
Ihned po prvním spuštění změňte `ADMIN_PASSWORD` v `.env` a restartujte aplikaci, nebo změňte heslo přes API:

```bash
curl -s -b cookies.txt -X PATCH http://localhost:8000/api/v1/users/admin \
  -H "Content-Type: application/json" \
  -d '{"password": "nove-silne-heslo"}'
```

**HTTPS**
V produkci provozujte UniForms výhradně za HTTPS reverzním proxy (nginx, Caddy). Cookie `uniforms_token` je označena `samesite=lax`, ale bez HTTPS může být zachycena.

**Platnost tokenu**
Výchozích 480 minut (8 hodin) je vhodné pro pracovní den. Pro zvýšenou bezpečnost snižte na 60–120 minut:

```ini
JWT_EXPIRE_MINUTES=60
```

**Brute-force ochrana**
Server vždy čeká 1 sekundu před odesláním chybové odpovědi `401`. Toto zpomalení je vestavěné a nelze ho vypnout konfigurací.

**Rotace klíče**
Při podezření na kompromitaci stačí změnit `JWT_SECRET_KEY` v `.env` — všechny existující tokeny přestanou být platné a uživatelé se musí znovu přihlásit.

> **Poznámka:** UniForms neimplementuje vlastní rate limiting na úrovni sítě. Pro produkční nasazení doplňte rate limiting na úrovni reverzního proxy (nginx `limit_req`, Cloudflare apod.).

---

## 7. Reference funkcí — `security.py`

| Funkce / závislost | Kde se používá | Popis |
|--------------------|----------------|-------|
| `hash_password(password)` | Při vytváření/změně uživatele | Vrátí bcrypt hash hesla. Plain text se nikam neukládá. |
| `verify_password(plain, hashed)` | `auth.py` — login endpoint | Porovná plain heslo s uloženým hashem. Vrací `bool`. |
| `create_access_token(data, expires_delta)` | `auth.py` — login endpoint | Vytvoří podepsaný JWT s claimy `sub`, `role`, `exp`. |
| `decode_token(token)` | `require_auth` | Dekóduje a ověří JWT podpis a expiraci. Vyhazuje PyJWT výjimky při neplatném tokenu. |
| `require_auth` | FastAPI `Depends()` na chráněných endpointech | Načte `uniforms_token` cookie, dekóduje JWT, vrátí `User`. Vrátí `401` pokud cookie chybí nebo je neplatná. |
| `require_admin` | FastAPI `Depends()` na admin endpointech | Zavolá `require_auth`, zkontroluje `role == "system_admin"`. Vrátí `403` jinak. |
| `require_collection_access` | `collection_deps.py` | Projde pro `system_admin` nebo uživatele s `collection_admin`/`collection_user` pro danou kolekci. Jinak `403`. |
| `require_collection_admin` | `collection_deps.py` | Projde pro `system_admin` nebo uživatele s `collection_admin` pro danou kolekci. Jinak `403`. |

### Modely

```python
class User(BaseModel):
    username: str
    role: str = "system_reader"   # systémová role uložená v JWT
    is_active: bool = True

class TokenPayload(BaseModel):
    sub: str            # username
    role: str           # system_admin | system_reader
    exp: Optional[int]  # Unix timestamp expirace

class LoginRequest(BaseModel):
    username: str
    password: str
```

---

> **Tip:** Pro testování v CI/CD prostředí nastavte `JWT_EXPIRE_MINUTES=5` a `AUTH_PROVIDER=simple` s testovacím uživatelem — tokeny vyprší rychle a nepředstavují bezpečnostní riziko při úniku testovacích logů.
