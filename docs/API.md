# UniForms – REST API

REST API projektu UniForms slouží k programatickému přístupu ke všem datům aplikace — záznamům, šablonám, kolekcím, uživatelům a nastavení. API je dostupné pod prefixem `/api/v1` na stejném portu jako webové rozhraní (výchozí: `http://localhost:8080`).

Veškerá komunikace probíhá ve formátu JSON. Autentizace je řešena přes httpOnly cookie `uniforms_token` (JWT HS256) — cookie se nastaví automaticky při přihlášení a prohlížeč ji posílá s každým dalším požadavkem.

**Interaktivní dokumentace:**
- Swagger UI: `http://localhost:8080/api/docs`
- ReDoc: `http://localhost:8080/api/redoc`

---

## Jak to funguje

Každý mutující požadavek (POST/PUT/PATCH/DELETE) nejdřív zachytí audit middleware a CSRF guard (`Content-Type: application/json`). Závislost `require_auth` pak ověří JWT a načte aktuální roli a aktivitu účtu z DB. Teprve poté handler zkontroluje oprávnění a zavolá příslušnou service vrstvu.

```
Prohlížeč / klient
    │
    │  HTTP request + Cookie: uniforms_token=<jwt>
    ▼
┌──────────────────────────────────────────────────┐
│  FastAPI (uvicorn, port 8080)                    │
│                                                  │
│  AuditMiddleware → data/audit/*.jsonl            │
│  SecurityMiddleware (CSRF guard, hlavičky)       │
│    ▼                                             │
│  require_auth: JWT + role/is_active z DB         │
│    ▼                                             │
│  Route handler                                   │
│    │                                             │
│    ├── /api/v1/auth/*          autentizace       │
│    ├── /api/v1/info/           veřejné info      │
│    ├── /api/v1/collections/*   kolekce           │
│    ├── /api/v1/records/*       záznamy           │
│    ├── /api/v1/templates/*     šablony           │
│    ├── /api/v1/users/*         správa uživatelů  │
│    ├── /api/v1/settings/*      nastavení cest    │
│    └── /api/v1/admin/*         admin: kolekce,   │
│                                role, audit,      │
│                                přístup, AM       │
│    ▼                                             │
│  Service vrstva → JSON soubory / SQLite          │
└──────────────────────────────────────────────────┘
    │
    ▼  JSON response
Prohlížeč / klient
```

### Rolový systém

Každý uživatel má **systémovou roli** a volitelně **kolekční roli** pro každou kolekci:

| Systémová role | Popis |
|----------------|-------|
| `system_admin` | Plný přístup ke všemu — správa uživatelů, nastavení, šablon, kolekcí |
| `system_reader` | Přístup pouze ke kolekcím, kde má přiřazenou kolekční roli |

| Kolekční role | Popis |
|---------------|-------|
| `collection_admin` | Správa šablon a záznamů v kolekci; může mazat záznamy |
| `collection_user` | Vytváření a editace záznamů; nelze mazat záznamy ani šablony |

`system_admin` má implicitně `collection_admin` oprávnění ve všech kolekcích.

---

## Autentizace

UniForms podporuje tři auth providery nastavitelné v `.env` proměnnou `AUTH_PROVIDER`:

| Provider | Popis |
|----------|-------|
| `simple` | Výchozí — bcrypt hash uložený v SQLite |
| `ldap` | LDAP/Active Directory |
| `oauth` | OAuth 2.0 / OIDC |

Po úspěšném přihlášení server nastaví cookie `uniforms_token` (JWT HS256). Token obsahuje claimy `sub` (username), `role` (systémová role) a `exp` (expirace). Platnost tokenu je `JWT_EXPIRE_MINUTES` minut (výchozí: 480 = 8 hodin).

Podrobnosti o bezpečnostní konfiguraci: [AUTENTIZACE.md](AUTENTIZACE.md)

---

## Rychlý start

Přihlášení a první požadavek přes `curl`:

```bash
# 1. Přihlášení — uloží cookie do souboru
curl -s -c /tmp/uf.cookies -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'

# 2. Seznam kolekcí s uloženou cookie
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/collections/

# 3. Vytvoření záznamu
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/records/soc/ \
  -H "Content-Type: application/json" \
  -d '{"template_id": "phishing-v1"}'

# 4. Odhlášení
curl -s -b /tmp/uf.cookies -c /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/auth/logout \
  -H "Content-Type: application/json"
```

---

## Autentizace – `/api/v1/auth`

Endpointy pro přihlášení, odhlášení a informace o přihlášeném uživateli.

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `POST` | `/api/v1/auth/login` | Přihlášení, nastaví httpOnly cookie | — |
| `POST` | `/api/v1/auth/logout` | Odhlášení, smaže cookie | — |
| `GET` | `/api/v1/auth/me` | Info o přihlášeném uživateli | povinná |

### `POST /api/v1/auth/login`

Ověří přihlašovací údaje a nastaví cookie `uniforms_token`. Při neúspěšném přihlášení server záměrně zpozdí odpověď o 1 sekundu (ochrana před brute-force útoky).

```bash
curl -s -c /tmp/uf.cookies -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

```json
// Tělo požadavku
{ "username": "admin", "password": "admin" }

// Odpověď 200 — nastaví Set-Cookie: uniforms_token=<jwt>; HttpOnly; SameSite=Lax
{ "access_token": "<jwt>", "token_type": "bearer" }

// Odpověď 401 — nesprávné přihlašovací údaje
{ "detail": "Nesprávné přihlašovací údaje" }
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `username` | ✓ | Uživatelské jméno |
| `password` | ✓ | Heslo v plaintextu |

### `POST /api/v1/auth/logout`

Smaže cookie `uniforms_token` a ukončí relaci.

```bash
curl -s -b /tmp/uf.cookies -c /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/auth/logout \
  -H "Content-Type: application/json"
```

```json
// Odpověď 200
{ "detail": "Odhlášení proběhlo úspěšně" }
```

### `GET /api/v1/auth/me`

Vrátí profil aktuálně přihlášeného uživatele načtený z JWT tokenu.

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/auth/me
```

```json
// Odpověď 200
{
  "username": "admin",
  "role": "system_admin",
  "is_active": true,
  "created_at": "2026-01-01T00:00:00"
}
```

---

## Veřejné info – `/api/v1/info`

Veřejný endpoint bez nutnosti autentizace. Vrací základní informace o aplikaci z konfigurace `uniforms.yaml`.

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/info/` | Název aplikace, verze, terminologie | — |

### `GET /api/v1/info/`

```bash
curl -s http://localhost:8080/api/v1/info/
```

```json
// Odpověď 200
{
  "app_name": "UniForms",
  "app_version": "1.0.0",
  "app_subtitle": "Universal Forms Engine"
}
```

---

## Kolekce – `/api/v1/collections`

Kolekce je logická skupina šablon a záznamů stejného charakteru (např. `soc`, `helpdesk`). Definice kolekcí jsou YAML soubory uložené v `data/collections/{id}.yaml`. Každá kolekce má vlastní terminologii, stavy workflow a přiřazení rolí.

`system_admin` vidí všechny kolekce. Ostatní uživatelé vidí pouze kolekce, kde mají přiřazenou kolekční roli.

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/collections/` | Seznam přístupných kolekcí | povinná |
| `GET` | `/api/v1/collections/{id}` | Detail jedné kolekce | povinná |

### `GET /api/v1/collections/`

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/collections/
```

```json
// Odpověď 200
[
  {
    "id": "soc",
    "name": "SOC",
    "description": "Security Operations Center",
    "terminology": {
      "record_id_label": "Ticket ID",
      "new_record_btn": "New Incident"
    },
    "workflow": {
      "initial_state": "new",
      "states": [
        { "id": "new",         "label": "Nový",         "color": "secondary" },
        { "id": "in_progress", "label": "Probíhá",      "color": "primary"   },
        { "id": "closed",      "label": "Uzavřeno",     "color": "success"   }
      ]
    },
    "list_columns": [
      { "key": "title",       "label": "Název"       },
      { "key": "record_owner", "label": "Koordinátor" }
    ],
    "id_format": {
      "prefix": "SOC",
      "format": "{prefix}-{YYYYMM}-{rand:04d}"
    },
    "roles": [
      { "id": "collection_admin", "label": "Správce kolekce" },
      { "id": "collection_user",  "label": "Uživatel kolekce" }
    ],
    "title_field": "title"
  }
]
```

### `GET /api/v1/collections/{id}`

Vrátí stejnou strukturu jako jeden prvek ze seznamu výše.

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/collections/soc
```

| Klíč (path) | ✓ | Popis |
|-------------|---|-------|
| `id` | ✓ | ID kolekce (slug, např. `soc`) |

---

## Záznamy – `/api/v1/records/{collection_id}`

Záznamy jsou JSON dokumenty uložené v `data/records/{collection_id}/`. Každý záznam vzniká naklonováním šablony z dané kolekce. ID záznamu generuje server dle formátu definovaného v konfiguraci kolekce (např. `SOC-202603-0042`).

Přístup k záznamům vyžaduje, aby měl uživatel přiřazenou kolekční roli (`collection_admin` nebo `collection_user`) nebo byl `system_admin`.

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/records/{collection_id}/` | Seznam záznamů (nejnovější první) | kolekce |
| `POST` | `/api/v1/records/{collection_id}/` | Vytvoření záznamu ze šablony | kolekce |
| `GET` | `/api/v1/records/{collection_id}/{record_id}` | Detail záznamu | kolekce |
| `PATCH` | `/api/v1/records/{collection_id}/{record_id}` | Aktualizace stavu a/nebo dat | kolekce |
| `DELETE` | `/api/v1/records/{collection_id}/{record_id}` | Smazání záznamu | collection_admin |
| `POST` | `/api/v1/records/{collection_id}/{record_id}/lock` | Získání zámku editace | kolekce |
| `DELETE` | `/api/v1/records/{collection_id}/{record_id}/lock` | Uvolnění zámku editace | kolekce |

### `GET /api/v1/records/{collection_id}/`

Vrátí seznam všech záznamů v kolekci seřazený od nejnovějšího.

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/records/soc/
```

```json
// Odpověď 200
[
  {
    "record_id": "SOC-202603-0042",
    "collection_id": "soc",
    "template_id": "phishing-v1",
    "status": "in_progress",
    "created_by": "user1",
    "created_at": "2026-03-05T14:30:22+00:00",
    "updated_at": "2026-03-05T15:00:10+00:00",
    "locked_by": null,
    "data": {}
  }
]
```

### `POST /api/v1/records/{collection_id}/`

Vytvoří nový záznam naklonováním zvolené šablony. Server vygeneruje ID dle formátu kolekce, nastaví stav na `initial_state` a zaznamená autora.

```bash
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/records/soc/ \
  -H "Content-Type: application/json" \
  -d '{"template_id": "phishing-v1"}'
```

```json
// Tělo požadavku
{ "template_id": "phishing-v1" }

// Odpověď 201
{
  "record_id": "SOC-202603-0042",
  "collection_id": "soc",
  "template_id": "phishing-v1",
  "status": "new",
  "created_by": "user1",
  "created_at": "2026-03-05T14:30:22+00:00",
  "updated_at": "2026-03-05T14:30:22+00:00",
  "locked_by": null,
  "data": { "sections": [] }
}
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `template_id` | ✓ | ID šablony, ze které se záznam vytvoří |

### `GET /api/v1/records/{collection_id}/{record_id}`

```bash
curl -s -b /tmp/uf.cookies \
  http://localhost:8080/api/v1/records/soc/SOC-202603-0042
```

```json
// Odpověď 200
{
  "record_id": "SOC-202603-0042",
  "collection_id": "soc",
  "template_id": "phishing-v1",
  "status": "in_progress",
  "created_by": "user1",
  "created_at": "2026-03-05T14:30:22+00:00",
  "updated_at": "2026-03-05T15:00:10+00:00",
  "locked_by": "user1",
  "data": { "sections": [] }
}
```

### `PATCH /api/v1/records/{collection_id}/{record_id}`

Aktualizuje stav a/nebo data záznamu. Všechna pole jsou volitelná — lze měnit pouze stav, pouze data nebo oboje najednou. Stav musí odpovídat platnému stavu workflow dané kolekce.

Zámek záznamu je vynucen na serveru: pokud záznam zamkl jiný uživatel, požadavek vrací `423 Locked` (s `locked_by` a `locked_at` v `detail`). Editovat lze záznam odemčený, nebo zamčený vlastním zámkem.

```bash
curl -s -b /tmp/uf.cookies \
  -X PATCH http://localhost:8080/api/v1/records/soc/SOC-202603-0042 \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress", "data": {"sections": []}}'
```

```json
// Pouze stav
{ "status": "in_progress" }

// Pouze data
{ "data": { "sections": [] } }

// Stav i data zároveň
{ "status": "closed", "data": { "sections": [] } }

// Odpověď 200 — aktualizovaný záznam
{
  "record_id": "SOC-202603-0042",
  "collection_id": "soc",
  "template_id": "phishing-v1",
  "status": "in_progress",
  "created_by": "user1",
  "created_at": "2026-03-05T14:30:22+00:00",
  "updated_at": "2026-03-05T15:10:00+00:00",
  "locked_by": "user1",
  "data": { "sections": [] }
}
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `status` | | Nový stav workflow (musí být platný stav pro danou kolekci) |
| `data` | | Objekt `{ "sections": [...] }` s aktualizovanými daty záznamu |

Stav mimo workflow kolekce vrací `422` s výčtem povolených stavů. Nezměněný stav projde
vždy – i u staršího záznamu, jehož stav ve workflow už není (jde ho dál ukládat).

```json
// Odpověď 422 — neznámý stav
{ "detail": "Unknown status 'bogus' – allowed: new, open, in_progress, on_hold, closed" }
```

`record_id` v cestě smí obsahovat jen písmena, číslice, `_` a `-`; jinak `400`
(u všech endpointů záznamů a zámků). Změna stavu a seznam změněných polí se zapisují
do [auditu](AUDIT.md).

### `DELETE /api/v1/records/{collection_id}/{record_id}`

Trvale smaže záznam. Vyžaduje roli `collection_admin` v dané kolekci nebo globální `system_admin`.

```bash
curl -s -b /tmp/uf.cookies \
  -X DELETE http://localhost:8080/api/v1/records/soc/SOC-202603-0042
```

```
// Odpověď 204 No Content
```

### Zámky editace – `lock`

Zámek zabraňuje souběžné editaci stejného záznamu dvěma uživateli. Před zahájením editace zámek získejte, po uložení ho uvolněte. `system_admin` může uvolnit cizí zámek.

**Platnost zámku je 30 minut** od posledního získání. Starší zámek se považuje za uvolněný
(zavřená záložka, pád prohlížeče) a kdokoli ho může převzít. Opakovaný `POST …/lock`
vlastníkem zámek obnoví – editor v prohlížeči to dělá každých 5 minut (heartbeat)
a při zavření stránky zámek uvolní (`pagehide`, `keepalive`).

#### `POST /api/v1/records/{collection_id}/{record_id}/lock`

```bash
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/records/soc/SOC-202603-0042/lock \
  -H "Content-Type: application/json"
```

```json
// Odpověď 200 — zámek získán
{ "locked_by": "user1" }

// Odpověď 423 — záznam zamkl jiný uživatel
{
  "detail": {
    "message": "Record is locked by another user",
    "locked_by": "user2",
    "locked_at": "2026-03-05T14:30:22+00:00"
  }
}
```

#### `DELETE /api/v1/records/{collection_id}/{record_id}/lock`

```bash
curl -s -b /tmp/uf.cookies \
  -X DELETE http://localhost:8080/api/v1/records/soc/SOC-202603-0042/lock
```

```
// Odpověď 204 No Content
```

> **Poznámka:** `system_admin` uvolní zámek i tehdy, kdy ho vlastní jiný uživatel. Běžný uživatel může uvolnit pouze svůj vlastní zámek.

---

## Šablony – `/api/v1/templates/{collection_id}`

Šablony jsou YAML soubory v `data/schemas/{collection_id}/`. Každá šablona definuje strukturu jednoho typu záznamu — sekce, pole, workflow. Čtení šablon je dostupné všem členům kolekce; správa (vytváření, editace, mazání) vyžaduje roli `collection_admin`.

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/templates/{collection_id}/` | Seznam šablon v kolekci | kolekce |
| `POST` | `/api/v1/templates/{collection_id}/` | Vytvoření šablony | collection_admin |
| `GET` | `/api/v1/templates/{collection_id}/{template_id}` | Normalizovaná šablona jako JSON | kolekce |
| `GET` | `/api/v1/templates/{collection_id}/{template_id}/source` | Zdrojový YAML pro editor | collection_admin |
| `PUT` | `/api/v1/templates/{collection_id}/{template_id}` | Uložení upraveného YAML | collection_admin |
| `DELETE` | `/api/v1/templates/{collection_id}/{template_id}` | Smazání šablony | collection_admin |

### `GET /api/v1/templates/{collection_id}/`

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/templates/soc/
```

```json
// Odpověď 200
[
  {
    "template_id": "phishing-v1",
    "name": "Phishing Incident",
    "version": "1.0",
    "status": "active",
    "abstract": false,
    "extends": null,
    "meta": {},
    "sections": [],
    "filename": "phishing.yaml"
  }
]
```

### `POST /api/v1/templates/{collection_id}/`

Vytvoří nový soubor šablony. Pokud soubor s daným názvem nebo šablona se stejným `template_id` již existuje, vrátí `409 Conflict`. Obsah se před uložením ověří – musí jít načíst jako šablona (YAML, `template_id`, dědičnost `extends`, normalizace, model `UniTemplate`); jinak `400 Bad Request` s popisem chyby. Rodičovská šablona (`extends`) proto musí existovat dřív než potomek.

```bash
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/templates/soc/ \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "malware",
    "content": "template_id: malware-v1\nname: Malware Incident\nversion: \"1.0\"\nsections: []\n"
  }'
```

```json
// Tělo požadavku
{
  "filename": "malware",
  "content": "template_id: malware-v1\nname: Malware Incident\nversion: \"1.0\"\nsections: []\n"
}

// Odpověď 200
{ "ok": true, "template_id": "malware-v1", "filename": "malware.yaml" }
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `filename` | ✓ | Slug názvu souboru bez přípony `.yaml` — povoleny znaky `[a-z0-9_-]` (přípona `.yaml` v hodnotě je tolerována a odstraní se) |
| `content` | ✓ | Celý obsah šablony jako YAML řetězec |

Nevalidní `filename` vrací `400`; nevalidní YAML v `content` také `400`.

### `GET /api/v1/templates/{collection_id}/{template_id}`

Vrátí šablonu normalizovanou do JSON — všechny v2 zkratky jsou rozvinuty, zděděné sekce jsou sloučeny.

```bash
curl -s -b /tmp/uf.cookies \
  http://localhost:8080/api/v1/templates/soc/phishing-v1
```

```json
// Odpověď 200 — normalizovaná šablona
{
  "template_id": "phishing-v1",
  "name": "Phishing Incident",
  "version": "1.0",
  "status": "active",
  "sections": []
}
```

### `GET /api/v1/templates/{collection_id}/{template_id}/source`

Vrátí zdrojový YAML přesně tak, jak je uložen na disku. Určeno pro editor v administraci.

```bash
curl -s -b /tmp/uf.cookies \
  http://localhost:8080/api/v1/templates/soc/phishing-v1/source
```

```json
// Odpověď 200
{
  "content": "template_id: phishing-v1\nname: Phishing Incident\nversion: \"1.0\"\nsections: []\n"
}
```

### `PUT /api/v1/templates/{collection_id}/{template_id}`

Přepíše zdrojový YAML šablony. Obsah se ověří stejně jako u `POST` (`400` s popisem chyby). `template_id` uvnitř YAML **nelze změnit** – pro nové ID vytvořte novou šablonu (jinak `400`).

```bash
curl -s -b /tmp/uf.cookies \
  -X PUT http://localhost:8080/api/v1/templates/soc/malware-v1 \
  -H "Content-Type: application/json" \
  -d '{"content": "template_id: malware-v1\nname: Malware Incident\nversion: \"1.1\"\nsections: []\n"}'
```

```json
// Tělo požadavku
{ "content": "template_id: malware-v1\nname: Malware Incident\nversion: \"1.1\"\nsections: []\n" }

// Odpověď 200
{ "ok": true, "filename": "malware.yaml" }
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `content` | ✓ | Nový obsah šablony jako YAML řetězec |

### `DELETE /api/v1/templates/{collection_id}/{template_id}`

```bash
curl -s -b /tmp/uf.cookies \
  -X DELETE http://localhost:8080/api/v1/templates/soc/malware-v1
```

```
// Odpověď 204 No Content
```

---

## Uživatelé – `/api/v1/users`

Správa uživatelských účtů. Všechny endpointy vyžadují globální roli `system_admin`.

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/users/` | Seznam všech uživatelů | system_admin |
| `POST` | `/api/v1/users/` | Vytvoření uživatele | system_admin |
| `GET` | `/api/v1/users/{username}` | Detail uživatele | system_admin |
| `PATCH` | `/api/v1/users/{username}` | Aktualizace role, stavu nebo hesla | system_admin |
| `DELETE` | `/api/v1/users/{username}` | Smazání uživatele | system_admin |
| `GET` | `/api/v1/users/{username}/collection-roles` | Kolekční role uživatele | system_admin |
| `PATCH` | `/api/v1/users/{username}/collection-roles` | Hromadná aktualizace kolekčních rolí | system_admin |

### `GET /api/v1/users/`

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/users/
```

```json
// Odpověď 200
[
  {
    "id": 1,
    "username": "admin",
    "role": "system_admin",
    "is_active": true,
    "created_at": "2026-01-01T00:00:00",
    "auth_source": "local"
  },
  {
    "id": 2,
    "username": "jsmith",
    "role": "system_reader",
    "is_active": true,
    "created_at": "2026-03-05T14:30:22",
    "auth_source": "access_manager"
  }
]
```

`auth_source`: `local` = přihlášení heslem, `access_manager` = OTP kód přes
access-manager (viz [ACCESS_MANAGER.md](ACCESS_MANAGER.md)). Efektivní přístup
včetně uživatelů realmu bez lokálního účtu vrací [`GET /api/v1/admin/access/`](#admin--přehled-přístupu--apiv1adminaccess).

### `POST /api/v1/users/`

Vytvoří nový uživatelský účet. Heslo je uloženo jako bcrypt hash. Při duplicitním uživatelském jménu vrátí `409 Conflict`.

```bash
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/users/ \
  -H "Content-Type: application/json" \
  -d '{"username": "jsmith", "password": "password123", "role": "system_reader"}'
```

```json
// Tělo požadavku
{ "username": "jsmith", "password": "password123", "role": "system_reader" }

// Odpověď 201
{
  "id": 2,
  "username": "jsmith",
  "role": "system_reader",
  "is_active": true,
  "created_at": "2026-03-05T14:30:22"
}
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `username` | ✓ | Uživatelské jméno (musí být unikátní) |
| `password` | ◐ | Heslo v plaintextu — server uloží bcrypt hash. Povinné pro `auth_source: "local"` (jinak `422`), u OTP účtu se ignoruje |
| `role` | | Systémová role: `system_admin` nebo `system_reader` (výchozí `system_reader`). U OTP účtu ji při každém přihlášení přepíšou skupiny realmu |
| `auth_source` | | `local` (výchozí) nebo `access_manager` |

### `GET /api/v1/users/{username}`

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/users/jsmith
```

```json
// Odpověď 200
{
  "id": 2,
  "username": "jsmith",
  "role": "system_reader",
  "is_active": true,
  "created_at": "2026-03-05T14:30:22"
}
```

### `PATCH /api/v1/users/{username}`

Aktualizuje roli, stav nebo heslo uživatele. Všechna pole jsou volitelná.

```bash
curl -s -b /tmp/uf.cookies \
  -X PATCH http://localhost:8080/api/v1/users/jsmith \
  -H "Content-Type: application/json" \
  -d '{"role": "system_admin", "is_active": true, "password": "newpassword456"}'
```

```json
// Odpověď 200
{
  "id": 2,
  "username": "jsmith",
  "role": "system_admin",
  "is_active": true,
  "created_at": "2026-03-05T14:30:22"
}
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `role` | | Nová systémová role: `system_admin` nebo `system_reader` (jiná hodnota → `422`) |
| `is_active` | | Aktivace (`true`) nebo deaktivace (`false`) účtu |
| `password` | | Nové heslo v plaintextu — server uloží bcrypt hash |
| `auth_source` | | Změna zdroje ověření: `local` nebo `access_manager` |

Deaktivace platí okamžitě (role a `is_active` se ověřují v DB při každém požadavku).

Vlastnímu účtu nelze odebrat admin roli ani ho deaktivovat (vrátí `400 Bad Request`) — ochrana proti zamknutí se ven z aplikace.

### `DELETE /api/v1/users/{username}`

Trvale smaže uživatelský účet i jeho role v kolekcích (nový účet se stejným jménem je nezdědí). Nelze smazat vlastní účet (vrátí `400 Bad Request`).

```bash
curl -s -b /tmp/uf.cookies \
  -X DELETE http://localhost:8080/api/v1/users/jsmith
```

```
// Odpověď 204 No Content
```

### `GET /api/v1/users/{username}/collection-roles`

Vrátí slovník všech kolekčních přiřazení uživatele ve formátu `{collection_id: role}`.

```bash
curl -s -b /tmp/uf.cookies \
  http://localhost:8080/api/v1/users/jsmith/collection-roles
```

```json
// Odpověď 200
{
  "soc": "collection_admin",
  "helpdesk": "collection_user"
}
```

### `PATCH /api/v1/users/{username}/collection-roles`

Hromadný upsert kolekčních přiřazení pro jednoho uživatele. Hodnota `null` pro danou kolekci přiřazení odebere. Kolekce neuvedené v požadavku zůstanou beze změny.

```bash
curl -s -b /tmp/uf.cookies \
  -X PATCH http://localhost:8080/api/v1/users/jsmith/collection-roles \
  -H "Content-Type: application/json" \
  -d '{
    "roles": {
      "soc": "collection_admin",
      "helpdesk": "collection_user",
      "old_collection": null
    }
  }'
```

```json
// Tělo požadavku — null = odebrat přiřazení
{
  "roles": {
    "soc": "collection_admin",
    "helpdesk": "collection_user",
    "old_collection": null
  }
}

// Odpověď 200 — aktuální přiřazení po změně
{
  "soc": "collection_admin",
  "helpdesk": "collection_user"
}
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `roles` | ✓ | Slovník `{collection_id: role}` — role je `collection_admin` nebo `collection_user` (jiná hodnota → `422`), `null` přiřazení odebere |

---

## Nastavení – `/api/v1/settings`

Konfigurace datových adresářů. Změny se projeví okamžitě bez restartu serveru. Všechny endpointy vyžadují globální roli `system_admin`. Povolené klíče: `records_dir`, `schemas_dir`, `collections_dir` — neznámý klíč vrací `422`.

> **Poznámka:** Nastavení z `.env` a `uniforms.yaml` (branding, auth provider, expirace JWT) jsou načtena pouze při startu a vyžadují restart serveru. Přes API lze měnit pouze nastavení cest uložená v SQLite.

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/settings/` | Aktuální nastavení | system_admin |
| `PATCH` | `/api/v1/settings/` | Aktualizace nastavení cest | system_admin |

### `GET /api/v1/settings/`

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/settings/
```

```json
// Odpověď 200
{
  "records_dir": "data/records",
  "collections_dir": "data/collections",
  "schemas_dir": "data/schemas"
}
```

Nastavení access-manageru (`am.*`, včetně aplikačního klíče) `GET /api/v1/settings/`
**nevrací** – mají vlastní API [`/api/v1/admin/access-manager`](#admin--access-manager--apiv1adminaccess-manager).

### `PATCH /api/v1/settings/`

Aktualizuje cesty k datovým adresářům. Každá hodnota musí být existující adresář bez `..` v cestě. Povolené klíče: `records_dir`, `schemas_dir`, `collections_dir`.

```bash
curl -s -b /tmp/uf.cookies \
  -X PATCH http://localhost:8080/api/v1/settings/ \
  -H "Content-Type: application/json" \
  -d '{
    "records_dir": "data/records",
    "collections_dir": "data/collections",
    "schemas_dir": "data/schemas"
  }'
```

```json
// Tělo požadavku
{
  "records_dir": "data/records",
  "collections_dir": "data/collections",
  "schemas_dir": "data/schemas"
}

// Odpověď 200 — aktuální stav po aktualizaci
{
  "records_dir": "data/records",
  "collections_dir": "data/collections",
  "schemas_dir": "data/schemas"
}
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `records_dir` | | Adresář pro JSON soubory záznamů (výchozí: `data/records`) |
| `collections_dir` | | Adresář pro YAML definice kolekcí (výchozí: `data/collections`) |
| `schemas_dir` | | Adresář pro YAML šablony kolekcí (výchozí: `data/schemas`) |

> **Pozor:** Zadaná cesta musí existovat na serveru a nesmí obsahovat `..`. Neplatná cesta vrátí `400 Bad Request`.

---

## Admin – Kolekce – `/api/v1/admin/collections`

Správa YAML definic kolekcí. Vyžaduje globální roli `system_admin`. Kolekce jsou uloženy v `data/collections/*.yaml`. Název souboru (`filename`) je zároveň ID kolekce — musí být slug tvořený znaky `[a-z0-9_-]`.

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/admin/collections/` | Seznam všech kolekcí | system_admin |
| `POST` | `/api/v1/admin/collections/` | Vytvoření kolekce | system_admin |
| `GET` | `/api/v1/admin/collections/{id}/source` | Zdrojový YAML kolekce | system_admin |
| `PUT` | `/api/v1/admin/collections/{id}` | Přepis YAML kolekce | system_admin |
| `DELETE` | `/api/v1/admin/collections/{id}` | Smazání kolekce | system_admin |

### `POST /api/v1/admin/collections/`

```bash
curl -s -b /tmp/uf.cookies \
  -X POST http://localhost:8080/api/v1/admin/collections/ \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "helpdesk",
    "content": "id: helpdesk\nname: Helpdesk\ndescription: IT helpdesk\nworkflow:\n  initial_state: new\n  states: []\n"
  }'
```

```json
// Tělo požadavku
{
  "filename": "helpdesk",
  "content": "id: helpdesk\nname: Helpdesk\n..."
}

// Odpověď 201
{ "collection_id": "helpdesk", "filename": "helpdesk.yaml" }
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `filename` | ✓ | Slug kolekce `[a-z0-9_-]` (bez přípony `.yaml`) |
| `content` | ✓ | Celý YAML obsah definice kolekce |

Obsah se před uložením přísně ověří (stejně u `PUT`), jinak `422` s popisem:

| Kontrola | Příklad chyby |
|----------|---------------|
| platný YAML, mapování | `Invalid YAML: …` |
| `id` = název souboru (role se párují podle `id`) | `Collection id 'zoo2' must match the file name 'zoo'` |
| `workflow.initial_state` je mezi `workflow.states` | `workflow.initial_state 'sleeping' is not one of: received, quarantine, …` |
| model `CollectionConfig` | `Invalid collection: 1 validation error …` |

Existující soubor se špatným `initial_state` se při načítání nezahodí – použije se první
stav a zaloguje varování.

### `GET /api/v1/admin/collections/{id}/source`

```bash
curl -s -b /tmp/uf.cookies \
  http://localhost:8080/api/v1/admin/collections/helpdesk/source
```

```json
// Odpověď 200
{ "content": "id: helpdesk\nname: Helpdesk\n..." }
```

### `PUT /api/v1/admin/collections/{id}`

```bash
curl -s -b /tmp/uf.cookies \
  -X PUT http://localhost:8080/api/v1/admin/collections/helpdesk \
  -H "Content-Type: application/json" \
  -d '{"content": "id: helpdesk\nname: IT Helpdesk\n..."}'
```

```json
// Odpověď 200
{ "collection_id": "helpdesk" }
```

### `DELETE /api/v1/admin/collections/{id}`

```bash
curl -s -b /tmp/uf.cookies \
  -X DELETE http://localhost:8080/api/v1/admin/collections/helpdesk
```

```
// Odpověď 204 No Content
```

---

## Admin – Kolekční role – `/api/v1/admin/collection-roles`

Správa přiřazení uživatelů ke kolekcím. Vyžaduje globální roli `system_admin`.

Kolekční role: `collection_admin` (správce — může mazat záznamy a editovat šablony), `collection_user` (běžný uživatel — může vytvářet a editovat záznamy).

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/admin/collection-roles/` | Všechna přiřazení z DB | system_admin |
| `PATCH` | `/api/v1/admin/collection-roles/{collection_id}` | Nahrání přiřazení pro kolekci | system_admin |

### Přehled oprávnění

| Akce | system_admin | collection_admin | collection_user |
|------|:---:|:---:|:---:|
| Zobrazit záznamy kolekce | ✓ | ✓ | ✓ |
| Vytvořit záznam | ✓ | ✓ | ✓ |
| Editovat pole záznamu | ✓ | ✓ | ✓ |
| Změnit stav workflow | ✓ | ✓ | ✓ |
| Smazat záznam | ✓ | ✓ | — |
| Zobrazit šablony | ✓ | ✓ | ✓ |
| Editovat / mazat šablony | ✓ | ✓ | — |
| Spravovat kolekční role | ✓ | — | — |

### `GET /api/v1/admin/collection-roles/`

```bash
curl -s -b /tmp/uf.cookies \
  http://localhost:8080/api/v1/admin/collection-roles/
```

```json
// Odpověď 200
[
  { "username": "alice", "collection_id": "soc",      "role": "collection_admin" },
  { "username": "bob",   "collection_id": "soc",      "role": "collection_user"  },
  { "username": "alice", "collection_id": "helpdesk", "role": "collection_user"  }
]
```

### `PATCH /api/v1/admin/collection-roles/{collection_id}`

Nahradí celou sadu přiřazení pro danou kolekci. Uživatelé neuvedení v požadavku přijdou o přiřazení k této kolekci.

```bash
curl -s -b /tmp/uf.cookies \
  -X PATCH http://localhost:8080/api/v1/admin/collection-roles/soc \
  -H "Content-Type: application/json" \
  -d '{
    "assignments": [
      { "username": "alice", "role": "collection_admin" },
      { "username": "bob",   "role": "collection_user"  }
    ]
  }'
```

```json
// Tělo požadavku
{
  "assignments": [
    { "username": "alice", "role": "collection_admin" },
    { "username": "bob",   "role": "collection_user"  }
  ]
}

// Odpověď 200 — aktuální přiřazení pro kolekci soc
{
  "collection_id": "soc",
  "assignments": [
    { "username": "alice", "role": "collection_admin" },
    { "username": "bob",   "role": "collection_user"  }
  ]
}
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `assignments` | ✓ | Pole objektů `{ username, role }` |
| `assignments[].username` | ✓ | Uživatelské jméno (musí existovat v DB) |
| `assignments[].role` | ✓ | Kolekční role: `collection_admin` nebo `collection_user` |

---

## Admin – Audit – `/api/v1/admin/audit`

Čtení auditní stopy (přihlášení a všechny změny přes API, i odmítnuté). Formát událostí
a význam polí: [AUDIT.md](AUDIT.md).

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/admin/audit/` | Události, nejnovější první | system_admin |

### `GET /api/v1/admin/audit/`

```bash
curl -s -b /tmp/uf.cookies \
  "http://localhost:8080/api/v1/admin/audit/?day_from=2026-11-01&who=demo&outcome=denied&limit=50"
```

```json
// Odpověď 200
{
  "day_from": "2026-11-01",
  "day_to": "2026-11-11",
  "count": 1,
  "truncated": false,
  "retention_days": 365,
  "events": [
    {
      "t": "2026-11-11T11:24:10+00:00",
      "kind": "write",
      "op": "update_record",
      "actor": "user:demo",
      "collection_id": "soc",
      "record_id": "UIB-11112026-8099",
      "method": "PATCH",
      "path": "/api/v1/records/soc/UIB-11112026-8099",
      "status": 423,
      "outcome": "denied",
      "error": "Record is locked by another user"
    }
  ]
}
```

| Parametr | ✓ | Popis |
|----------|:-:|-------|
| `day_from`, `day_to` | | `RRRR-MM-DD`, včetně; výchozí posledních 7 dní |
| `who` | | podřetězec aktéra nebo subjektu (`demo` najde `user:demo`) |
| `kind` | | `auth` \| `write` |
| `outcome` | | `ok` \| `denied` \| `rejected` \| `error` |
| `collection_id` | | jen události dané kolekce |
| `text` | | fulltext přes celou událost (ID záznamu, IP …) |
| `limit` | | 1–5000, výchozí 500; `truncated: true` = výsledků je víc |

---

## Admin – Přehled přístupu – `/api/v1/admin/access`

Kdo se do UniForms dostane a v jaké roli – lokální účty i uživatelé realmu access-manageru,
bez ohledu na to, kdo je autentizační a kdo autorizační autorita. Podklad stránky
Admin → Users.

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/admin/access/` | Efektivní přístup všech účtů | system_admin |

### `GET /api/v1/admin/access/`

```bash
curl -s -b /tmp/uf.cookies http://localhost:8080/api/v1/admin/access/
```

```json
// Odpověď 200
{
  "auth_provider": "simple",
  "local": [
    { "username": "demo", "role": "system_admin", "is_active": true, "auth_source": "local",
      "created_at": "2026-11-11 09:38:45", "access": "system_admin", "reason": null }
  ],
  "access_manager": {
    "configured": true,
    "realm": "uniforms.example.com",
    "admin_group": "uniforms-admin",
    "user_group": "uniforms-user",
    "error": null,
    "users": [
      { "username": "hana", "enabled": true, "groups": ["uniforms-user", "user"],
        "role": "system_reader", "in_realm": true, "local": null,
        "access": "system_reader", "reason": null },
      { "username": "petr", "enabled": true, "groups": ["user"],
        "role": null, "in_realm": true, "local": null,
        "access": null, "reason": "not in uniforms-user / uniforms-admin" }
    ]
  }
}
```

| Pole | Popis |
|------|-------|
| `access` | efektivní role v UniForms, nebo `null` = bez přístupu |
| `reason` | proč bez přístupu: `inactive`, `disabled in realm`, `not in <user> / <admin>`, `blocked locally (inactive)`, `name taken by a local password account`, `not in realm – cannot sign in`, `password login disabled (AUTH_PROVIDER=access_manager)` |
| `access_manager.users[].role` | role, kterou dávají skupiny realmu |
| `access_manager.users[].local` | lokální řádek (`null` = vznikne při prvním přihlášení) |
| `access_manager.users[].in_realm` | `false` = lokální OTP účet, jehož identita z realmu zmizela |
| `access_manager.error` | access-manager nedostupný – lokální část se vrátí i tak |

---

## Admin – Access-manager – `/api/v1/admin/access-manager`

Napojení na access-manager z GUI (Settings). Hodnoty mají přednost před `.env`.
Aplikační klíč je **jen pro zápis** – žádný endpoint ho nevrací. Postup a význam polí:
[ACCESS_MANAGER.md](ACCESS_MANAGER.md).

| Metoda | Endpoint | Popis | Auth |
|--------|----------|-------|------|
| `GET` | `/api/v1/admin/access-manager/` | Efektivní konfigurace a zdroj hodnot | system_admin |
| `PUT` | `/api/v1/admin/access-manager/` | Uložení | system_admin |
| `POST` | `/api/v1/admin/access-manager/test` | Test připojení (i neuložených hodnot) | system_admin |

### `GET /api/v1/admin/access-manager/`

```json
// Odpověď 200
{
  "configured": true,
  "fields": {
    "url":           { "value": "https://access-manager.example.com", "source": "gui" },
    "realm":         { "value": "uniforms.example.com", "source": "gui" },
    "ca":            { "value": "", "source": "default" },
    "admin_group":   { "value": "uniforms-admin", "source": "default" },
    "user_group":    { "value": "uniforms-user", "source": "default" },
    "auth_provider": { "value": "simple", "source": "env" }
  },
  "key": { "set": true, "source": "gui", "key_id": "k1" },
  "local_mode": false
}
```

`source`: `gui` (uloženo v Settings) | `env` | `default`. `key_id` je veřejná část klíče
(`am_k1_…` → `k1`).

### `PUT /api/v1/admin/access-manager/`

```bash
curl -s -b /tmp/uf.cookies \
  -X PUT http://localhost:8080/api/v1/admin/access-manager/ \
  -H "Content-Type: application/json" \
  -d '{"url": "https://access-manager.example.com", "realm": "uniforms.example.com", "key": "am_k1_<klíč z konzole>"}'
```

```json
// Odpověď 200 — tvar jako GET + seznam změněných polí
{
  "ok": true,
  "changed": ["key", "realm", "url"],
  "configured": true,
  "fields": { "url": { "value": "https://access-manager.example.com", "source": "gui" } },
  "key": { "set": true, "source": "gui", "key_id": "k1" },
  "local_mode": false
}
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `url` | | `https://…`; plain `http` jen na loopback (jinak `422`) |
| `realm` | | název realmu |
| `key` | | aplikační klíč `am_k…_…` (jinak `422`); `""` odebere klíč uložený v GUI |
| `admin_group`, `user_group` | | skupiny realmu pro `system_admin` / `system_reader` |
| `auth_provider` | | `simple` \| `access_manager`; `""` = zpět na `.env` |
| `ca` | | cesta k vlastní CA |

Vynechané pole se nemění, prázdný řetězec vrátí platnost `.env` / výchozí hodnotě.
`auth_provider: "access_manager"` uložený správcem přihlášeným lokálním heslem vrací
`409` (zamkl by se). Do auditu jdou jen názvy změněných polí.

### `POST /api/v1/admin/access-manager/test`

Tělo má tvar jako `PUT` (všechna pole volitelná – chybějící se doplní z efektivní
konfigurace). Nic se neukládá.

```json
// Odpověď 200 — úspěch
{
  "ok": true,
  "message": "Connected to realm 'uniforms.example.com': 4 users, groups OK.",
  "ready": true,
  "not_ready_reason": null,
  "users": 4,
  "groups": ["uniforms-admin", "uniforms-user", "user"],
  "missing_groups": [],
  "realm": "uniforms.example.com"
}

// Odpověď 200 — neúspěch (HTTP 200, ok: false)
{ "ok": false, "message": "RuntimeError: realm nesouhlasi: ocekavano 'soc.example.com', sluzba hlasi 'uniforms.example.com'" }
```

---

## Vzory chybových odpovědí

Všechny chyby vracejí JSON tělo ve standardním formátu:

```json
// Standardní chyba
{ "detail": "Popis chyby" }

// Chyba 423 Locked — rozšířený formát s informacemi o zámku
{
  "detail": {
    "message": "Record is locked by another user",
    "locked_by": "user2",
    "locked_at": "2026-03-05T14:30:22+00:00"
  }
}

// Chyba 422 Unprocessable Entity — validační chyba Pydantic
{
  "detail": [
    {
      "loc": ["body", "username"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

Typické scénáře:

| Situace | Kód | `detail` |
|---------|-----|---------|
| Špatné přihlašovací údaje | 401 | `"Nesprávné přihlašovací údaje"` |
| Chybějící nebo expirovaný token | 401 | `"Not authenticated"` |
| Nedostatečná oprávnění | 403 | `"Not enough permissions"` |
| Záznam / šablona / kolekce neexistuje | 404 | `"Record 'X' not found"` apod. |
| Duplicitní username nebo soubor | 409 | `"Uživatel 'X' již existuje"` apod. |
| Neplatný YAML | 400 | popis chyby parseru |
| Neplatná cesta (settings) | 400 | popis chyby validace |
| Záznam zamkl jiný uživatel | 423 | objekt s `locked_by` a `locked_at` |
| Pokus smazat vlastní účet | 400 | `"Nelze smazat vlastní účet"` |
| Neplatné `record_id` v cestě | 400 | `"Invalid record_id – only letters, digits, '_' and '-' are allowed"` |
| Neplatná šablona při uložení / změna `template_id` | 400 | `"Invalid template: …"` |
| Neplatná kolekce při uložení | 422 | `"workflow.initial_state … is not one of: …"` apod. |
| Stav záznamu mimo workflow | 422 | `"Unknown status 'X' – allowed: …"` |
| Účet deaktivován / smazán během session | 401 | `"Account disabled or removed – please log in again"` |
| Příliš mnoho pokusů o OTP přihlášení | 429 | `"Příliš mnoho pokusů – zkuste to znovu za N s"` |

---

## HTTP stavové kódy

| Kód | Název | Kdy |
|-----|-------|-----|
| `200` | OK | Úspěch — GET, PATCH, PUT |
| `201` | Created | Vytvořen záznam nebo uživatel |
| `204` | No Content | Smazání nebo uvolnění zámku |
| `400` | Bad Request | Neplatné tělo požadavku (např. chybný YAML, zakázaná cesta, smazání vlastního účtu) |
| `401` | Unauthorized | Chybějící, expirovaný nebo neplatný JWT token |
| `403` | Forbidden | Nedostatečná oprávnění (vyžadována vyšší role) |
| `404` | Not Found | Záznam, šablona, kolekce nebo uživatel neexistuje |
| `409` | Conflict | Duplicitní username nebo soubor se zadaným názvem již existuje |
| `415` | Unsupported Media Type | Chybí `Content-Type: application/json` u POST/PUT/PATCH |
| `422` | Unprocessable Entity | Validační chyba těla požadavku (Pydantic), neplatná kolekce, stav mimo workflow |
| `423` | Locked | Záznam zamkl jiný uživatel |
| `429` | Too Many Requests | access-manager omezil pokusy o přihlášení |

---

## Reference

- Interaktivní dokumentace (Swagger UI): `http://localhost:8080/api/docs`
- Interaktivní dokumentace (ReDoc): `http://localhost:8080/api/redoc`
- Autentizace a konfigurace: [AUTENTIZACE.md](AUTENTIZACE.md)
- Přihlášení přes access-manager: [ACCESS_MANAGER.md](ACCESS_MANAGER.md)
- Auditní stopa: [AUDIT.md](AUDIT.md)
- Tvorba šablon a záznamů: [SABLONY.md](SABLONY.md)
- Konfigurace kolekcí: [KOLEKCE.md](KOLEKCE.md)
- Frontend rendering: [FRONTEND.md](FRONTEND.md)
- Použití jako knihovna: [KNIHOVNA.md](KNIHOVNA.md)
- Instalace a nasazení: [INSTALACE.md](INSTALACE.md)
