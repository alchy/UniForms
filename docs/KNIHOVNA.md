# UniForms jako knihovna

UniForms není jen samostatná aplikace — balíček `uniforms` je navržen jako knihovna, kterou lze vložit do vlastního programu. Tento dokument popisuje veřejné API balíčku, způsoby integrace a body rozšíření.

## Veřejné API

```python
from uniforms import create_app, configure, Settings, UniformsConfig, load_uniforms_config
```

| Symbol | Popis |
|--------|-------|
| `create_app(...)` | Tovární funkce — vrátí nakonfigurovanou FastAPI aplikaci |
| `configure(...)` | Přenastaví globální konfiguraci (volat před `create_app`) |
| `Settings` | Infrastrukturní nastavení (ekvivalent `.env`) |
| `UniformsConfig` | Doménová konfigurace (ekvivalent `uniforms.yaml`) |
| `load_uniforms_config(path)` | Načte `UniformsConfig` z YAML souboru |

## Vrstvy balíčku

Balíček je rozdělen do vrstev; každou lze použít samostatně:

```
uniforms/
├── main.py       HTTP vrstva — create_app() skládá routery, middleware, static
├── api/v1/       REST API routery (FastAPI)
├── web/          server-side rendering (Jinja2) — volitelné (include_web)
├── services/     doménová logika BEZ závislosti na HTTP
│                 (record_service, template_service, collection_service)
├── storage/      StorageBackend — rozhraní úložiště záznamů + souborová implementace
├── auth/         AuthProvider — rozhraní autentizace + simple/ldap/oauth
├── core/         security (JWT, bcrypt), SQLite, validace vstupů, middleware
└── models/       Pydantic modely (UniRecord, UniTemplate, CollectionConfig, User)
```

Šablony a statické soubory jsou uvnitř balíčku a načítají se relativně k němu — integrace nezávisí na pracovním adresáři hostitele. Datové cesty (`data/records`, SQLite…) se konfigurují přes `Settings`.

## Scénáře integrace

### 1. Samostatná aplikace s vlastní konfigurací

```python
from uniforms import configure, create_app

configure(uniforms_path="konfigurace/helpdesk.yaml")
app = create_app()
# uvicorn modul:app
```

### 2. Programová konfigurace (bez .env / uniforms.yaml)

```python
from uniforms import Settings, UniformsConfig, create_app

app = create_app(
    settings=Settings(
        jwt_secret_key="…silný náhodný klíč…",
        cookie_secure=True,
        database_path="/var/lib/mujsystem/uniforms.db",
        default_records_dir="/var/lib/mujsystem/records",
    ),
    uniforms_config=UniformsConfig(),   # nebo load_uniforms_config(cesta)
)
```

### 3. Sub-aplikace hostitelského FastAPI

```python
from fastapi import FastAPI
from uniforms import create_app

host = FastAPI()
host.mount("/forms", create_app())
```

REST API je pak dostupné pod `/forms/api/v1/…`, statické soubory pod `/forms/static/…`.

> **Omezení:** HTML UI generuje absolutní cesty (`/login`, `/api/v1/…`), plnohodnotné je proto při mountu na kořen domény nebo vlastní subdoméně. Pro mount pod prefix použijte `include_web=False` a vlastní frontend, nebo provozujte UI na samostatné (sub)doméně.

### 4. Jen REST API (headless)

```python
app = create_app(include_web=False, docs_url=None)
```

Hostitel dodá vlastní frontend; UniForms slouží jako datové API pro šablony, záznamy, workflow a zamykání.

## Body rozšíření

### Vlastní úložiště záznamů

Implementuj rozhraní `uniforms.storage.base.StorageBackend` (CRUD + zámky) — např. Elasticsearch nebo MongoDB — a nahraď dependency `uniforms.storage.get_storage`:

```python
from uniforms.storage import get_storage
app.dependency_overrides[get_storage] = my_get_storage
```

### Vlastní autentizace

Implementuj `uniforms.auth.auth_provider.AuthProvider` (`authenticate`, `get_user`). Připravené stuby: `LDAPProvider`, `OAuthProvider` (`uniforms/auth/`). Aktivace přes `AUTH_PROVIDER` v `.env`, nebo dependency override `uniforms.api.v1.auth.get_auth_provider`.

### Vlastní typ sekce formuláře (JS)

```javascript
UniForms.registerRenderer('muj_typ', (section) => {
    const el = document.createElement('div');
    /* … */
    return el;
});
```

Renderer dostane objekt sekce (JSON ze záznamu) a vrací DOM element. Sdílené pomocné funkce jsou v `UniForms._helpers`.

## Použití služeb bez HTTP vrstvy

Doménová logika ve `uniforms/services/` nemá závislost na FastAPI — lze ji volat přímo (např. z CLI skriptu nebo dávkového importu):

```python
from pathlib import Path
from uniforms.services import record_service
from uniforms.storage.file_backend import FileStorageBackend

storage = FileStorageBackend(Path("data/records/helpdesk"))
records = await record_service.list_records(storage)
```
