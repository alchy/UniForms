# UniForms

Generický formulářový engine pro strukturovaný sběr dat. Šablony definuješ v YAML, záznamy vyplňuješ v prohlížeči, správu zajišťuje REST API.

## Co je UniForms?

UniForms je webová aplikace, která transformuje YAML definice šablon na interaktivní HTML formuláře. Analytik otevře záznam v prohlížeči, vyplní strukturovaný formulář vygenerovaný ze šablony a uloží. Aplikace se stará o ukládání, zamykání, stavy workflow a správu uživatelů.

UniForms je doménově nezávislý. Stejný engine může pohánět IT helpdesk tickety, HR onboardingové žádosti, bezpečnostní incidenty SOC, auditní checklisty nebo jakýkoliv jiný strukturovaný workflow — doménu definuješ výhradně šablonami a konfigurací.

## Klíčové vlastnosti

- **YAML šablony** — strukturu formuláře (sekce, pole, checklisty, tabulky) definuješ v čitelném YAML; pro nový typ záznamu nepotřebuješ psát kód
- **Extension systém** — doménově specifické renderery a šablony zabalené jako extension (např. extension `soc` přidává SOC/CSIRT workbooky)
- **Konfigurovatelná terminologie** — štítky jako „záznam", „šablona" nebo názvy stavů workflow čte aplikace z `uniforms.yaml`; UI reflektuje jazyk tvé domény
- **Souborové úložiště** — záznamy jsou JSON soubory na disku; cesta je konfigurovatelná; žádná externí databáze
- **JWT autentizace** — httpOnly cookie (`uniforms_token`), rolový přístup (admin / uživatel), konfigurovatelná délka session
- **Workflow stavy** — každá kolekce definuje vlastní sadu stavů s barvami a popisky
- **Dědičnost šablon** — šablona může dědit sekce z nadřazené šablony; podporovány abstraktní základní šablony
- **Zamykání záznamů** — brání souběžné editaci; zámek se získá při otevření, uvolní při uložení a odchodu
- **Tisková verze** — čistý tiskový layout přes `window.print()` nebo uložení do PDF

## Rychlý start

```bash
git clone https://github.com/alchy/UniForms.git
cd UniForms
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # nastav JWT_SECRET_KEY a ADMIN_PASSWORD
python scripts/download_vendors.py
python start.py
```

Aplikace je dostupná na **http://localhost:8080**. Výchozí přihlášení: `admin` / `admin`.

> **Pozor:** Výchozí heslo okamžitě změň přes Admin → Users.

## Konfigurace

### `.env` — tajné klíče a infrastruktura

```ini
JWT_SECRET_KEY=vygeneruj-silny-klic-min-32-znaku   # POVINNÉ — změň!
JWT_EXPIRE_MINUTES=480
AUTH_PROVIDER=simple        # simple | ldap | oauth
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin        # změň!
DATABASE_PATH=data/uniforms.db
```

### `uniforms.yaml` — konfigurace domény

Doménová nastavení (terminologie, výchozí workflow, extensions) patří do `uniforms.yaml`, ne do `.env`:

```yaml
app:
  name: "UniForms"
  subtitle: "Universal Forms Engine"

terminology:
  record: "záznam"
  records: "záznamy"

workflow:
  default_states:
    - id: new
      label: "Nové"
      color: secondary
    - id: in_progress
      label: "V řešení"
      color: warning
    - id: closed
      label: "Uzavřeno"
      color: success
  initial_state: new

extensions:
  - id: soc
    path: extensions/soc
```

## Technický stack

- **Backend**: FastAPI + Uvicorn (Python 3.11+)
- **Frontend**: Jinja2 + Bootstrap 5 (server-side rendering)
- **Auth**: JWT (PyJWT), httpOnly cookie `uniforms_token`, bcrypt hesla
- **Databáze**: SQLite — uživatelé, nastavení, zámky (aiosqlite)
- **Úložiště**: JSON soubory (záznamy), YAML soubory (šablony, kolekce)
- **JS knihovny**: Bootstrap Icons, DataTables, Ace Editor
- **Form renderer**: `uniforms.js` — browser-side JSON → interaktivní HTML formulář

## Dokumentace

| Soubor | Obsah |
|--------|-------|
| [docs/INSTALACE.md](docs/INSTALACE.md) | Instalace, konfigurace, produkční nasazení |
| [docs/API.md](docs/API.md) | REST API — přehled všech endpointů |
| [docs/AUTENTIZACE.md](docs/AUTENTIZACE.md) | Auth, role, JWT, správa uživatelů |
| [docs/KOLEKCE.md](docs/KOLEKCE.md) | Formát `collection.yaml` — workflow, terminologie, id_format |
| [docs/SABLONY.md](docs/SABLONY.md) | YAML šablony — typy sekcí, pole, pipeline, dědičnost |
| [docs/FRONTEND.md](docs/FRONTEND.md) | Web routing, uniforms.js renderer, extension systém |
| [docs/HOW2WRITE.md](docs/HOW2WRITE.md) | Styl psaní technické dokumentace (pro přispěvatele) |
