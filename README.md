# UniForms

Generický formulářový engine pro strukturovaný sběr dat — jako samostatná aplikace **i jako Python knihovna**. Šablony definuješ v YAML, záznamy vyplňuješ v prohlížeči, správu zajišťuje REST API.

## Co je UniForms?

UniForms je balíček `uniforms`, který transformuje YAML definice šablon na interaktivní HTML formuláře. Analytik otevře záznam v prohlížeči, vyplní strukturovaný formulář vygenerovaný ze šablony a uloží. Engine se stará o ukládání, zamykání, stavy workflow a správu uživatelů.

UniForms je doménově nezávislý. Stejný engine může pohánět IT helpdesk tickety, HR onboardingové žádosti, bezpečnostní incidenty SOC, auditní checklisty nebo jakýkoliv jiný strukturovaný workflow — doménu definuješ výhradně šablonami a konfigurací.

## Klíčové vlastnosti

- **YAML šablony** — strukturu formuláře (sekce, pole, checklisty, tabulky) definuješ v čitelném YAML; pro nový typ záznamu nepotřebuješ psát kód
- **Knihovna i aplikace** — `create_app()` vrací FastAPI aplikaci, kterou lze spustit samostatně, nebo namountovat do hostitelské aplikace; služby a rozhraní (`StorageBackend`, `AuthProvider`) lze použít i bez HTTP vrstvy
- **Konfigurovatelná terminologie** — doménové pojmy („Ticket ID", „Assigned To"…) čte engine z `uniforms.yaml`; kolekce je mohou přepsat per-kolekce
- **Souborové úložiště** — záznamy jsou JSON soubory na disku; cesta je konfigurovatelná; žádná externí databáze (SQLite jen pro uživatele a nastavení)
- **JWT autentizace** — httpOnly cookie (`uniforms_token`), role `system_admin` / `system_reader` + role per kolekce, konfigurovatelná délka session
- **Workflow stavy** — každá kolekce definuje vlastní sadu stavů s barvami a popisky
- **Dědičnost šablon** — šablona může dědit sekce z nadřazené šablony; podporovány abstraktní základní šablony
- **Zamykání záznamů** — brání souběžné editaci; zámek je vynucen i na serveru (PATCH zamčeného záznamu vrací HTTP 423)
- **Tisková verze** — čistý tiskový layout přes `window.print()` nebo uložení do PDF

## Rychlý start (samostatná aplikace)

```bash
git clone https://github.com/alchy/UniForms.git
cd UniForms
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # nastav JWT_SECRET_KEY a ADMIN_PASSWORD
python scripts/download_vendors.py
python start.py                  # spustí uvicorn uniforms.main:app
```

Aplikace je dostupná na **http://localhost:8080**. Výchozí přihlášení: `admin` / `admin`.

> **Pozor:** Výchozí heslo okamžitě změň přes Admin → Users. Aplikace při startu loguje varování, dokud běží s výchozím heslem nebo výchozím JWT klíčem.

## Použití jako knihovna

UniForms je navržen tak, aby šel vložit do jiné aplikace. Veřejné API balíčku:

```python
from uniforms import create_app, configure, Settings, UniformsConfig
```

**Samostatná aplikace s vlastní konfigurací:**

```python
from uniforms import configure, create_app

configure(uniforms_path="konfigurace/helpdesk.yaml")   # doménová konfigurace
app = create_app()                                     # plná aplikace (UI + API)
```

**Sub-aplikace hostitelského FastAPI:**

```python
from fastapi import FastAPI
from uniforms import create_app

host = FastAPI()
host.mount("/forms", create_app())    # REST API: /forms/api/v1/..., UI: /forms/...
```

**Jen REST API bez HTML UI** (hostitel dodá vlastní frontend):

```python
app = create_app(include_web=False)
```

Parametry `create_app(settings=..., uniforms_config=...)` přepíší konfiguraci programově (ekvivalent `.env` / `uniforms.yaml`). Cesty k šablonám a statickým souborům jsou relativní k balíčku, takže nezávisí na pracovním adresáři hostitele; datové cesty (`data/…`) se konfigurují přes `Settings`.

**Body rozšíření:**

| Rozhraní | Účel |
|----------|------|
| `uniforms.storage.base.StorageBackend` | vlastní úložiště záznamů (Elasticsearch, MongoDB, …) |
| `uniforms.auth.auth_provider.AuthProvider` | vlastní autentizace (LDAP, OAuth2) |
| `uniforms.services.*` | doménová logika (záznamy, šablony, kolekce) použitelná bez HTTP vrstvy |
| `UniForms.registerRenderer(type, fn)` (JS) | vlastní typ sekce formuláře v prohlížeči |

> Pozn.: HTML UI používá absolutní cesty (`/login`, `/api/v1/…`), plnohodnotné je proto při mountu na kořen domény (nebo vlastní subdoméně). Při mountu pod prefix (`/forms`) je plně funkční REST API; UI pod prefixem je na roadmapě.

## Konfigurace

### `.env` — tajné klíče a infrastruktura

```ini
JWT_SECRET_KEY=vygeneruj-silny-klic-min-32-znaku   # POVINNÉ — změň!
JWT_EXPIRE_MINUTES=480
COOKIE_SECURE=true          # v produkci za HTTPS
AUTH_PROVIDER=simple        # simple | ldap | oauth
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin        # změň!
DATABASE_PATH=data/uniforms.db
```

### `uniforms.yaml` — konfigurace domény

Všechny klíče jsou volitelné; neuvedené hodnoty mají výchozí nastavení. Stačí přepsat doménové pojmy — kompletní katalog UI textů je v `TerminologyConfig` (`uniforms/config.py`):

```yaml
app:
  name: "IT ServiceDesk"
  subtitle: "IT Ticket Management"

terminology:
  record_id_label: "Ticket ID"
  record_owner_label: "Assigned To"
  new_record_btn: "New Ticket"
  take_over_btn: "Assign to Me"

id:
  prefix: "TKT"
  format: "{prefix}-{YYYYMM}-{rand:04d}"

# výchozí workflow — stejná struktura jako `workflow:` v collection YAML
workflow:
  initial_state: new
  states:
    - { id: new,         label: "New",         color: secondary }
    - { id: in_progress, label: "In Progress", color: warning }
    - { id: closed,      label: "Closed",      color: success }
```

> **Změna syntaxe:** dřívější klíč `workflow.default_states` byl přejmenován na `workflow.states` (sjednoceno s formátem kolekcí). Klíč `extensions` byl odstraněn — rozšíření rendereru se registrují v JS přes `UniForms.registerRenderer`.

## Struktura balíčku

```
uniforms/            Python balíček (knihovna + aplikace)
├── main.py          create_app() — tovární funkce FastAPI aplikace
├── config.py        Settings (.env) + UniformsConfig (uniforms.yaml), configure()
├── api/v1/          REST API routery
├── web/             server-side rendering (Jinja2)
├── core/            security (JWT, bcrypt), databáze, validace, middleware
├── services/        doménová logika (záznamy, šablony, kolekce, nastavení)
├── storage/         StorageBackend rozhraní + souborová implementace
├── auth/            AuthProvider rozhraní + simple/ldap/oauth implementace
├── models/          Pydantic modely
├── templates/       Jinja2 šablony UI
└── static/          JS (main, uniforms, records_list, record_detail), CSS, vendor
data/                runtime data (SQLite, záznamy, šablony, kolekce)
```

## Technický stack

- **Backend**: FastAPI + Uvicorn (Python 3.11+)
- **Frontend**: Jinja2 + Bootstrap 5 (server-side rendering)
- **Auth**: JWT (PyJWT), httpOnly cookie `uniforms_token`, bcrypt hesla
- **Databáze**: SQLite — uživatelé, nastavení, role kolekcí (aiosqlite)
- **Úložiště**: JSON soubory (záznamy), YAML soubory (šablony, kolekce)
- **JS knihovny**: Bootstrap Icons, DataTables, Ace Editor
- **Form renderer**: `uniforms.js` — browser-side JSON → interaktivní HTML formulář

## Dokumentace

| Soubor | Obsah |
|--------|-------|
| [docs/KNIHOVNA.md](docs/KNIHOVNA.md) | Použití UniForms jako knihovny — embedding, rozšíření |
| [docs/INSTALACE.md](docs/INSTALACE.md) | Instalace, konfigurace, produkční nasazení |
| [docs/API.md](docs/API.md) | REST API — přehled všech endpointů |
| [docs/AUTENTIZACE.md](docs/AUTENTIZACE.md) | Auth, role, JWT, správa uživatelů |
| [docs/KOLEKCE.md](docs/KOLEKCE.md) | Formát `collection.yaml` — workflow, terminologie, id_format |
| [docs/SABLONY.md](docs/SABLONY.md) | YAML šablony — typy sekcí, pole, pipeline, dědičnost |
| [docs/FRONTEND.md](docs/FRONTEND.md) | Web routing, uniforms.js renderer, JS moduly |
| [docs/HOW2WRITE.md](docs/HOW2WRITE.md) | Styl psaní technické dokumentace (pro přispěvatele) |
