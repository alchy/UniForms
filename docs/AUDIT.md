# Auditní stopa

UniForms zapisuje **každé přihlášení a každou změnu provedenou přes API** – včetně
pokusů, které byly odmítnuty – do auditní stopy. Odpovídá na otázku *kdo, co, kdy,
odkud a jestli to prošlo*. Dokument je pro správce (čtení auditu) a pro vývojáře
(co a jak se zapisuje).

Audit vidí jen **system_admin** (Admin → Audit). Formát je převzatý z auditu
[access-manageru](https://github.com/alchy/access-manager).

---

## Co to je a k čemu slouží?

- Dohledat, **kdo změnil záznam** (a které pole), kdo ho smazal, kdo měnil šablonu,
  kolekci nebo uživatele.
- Vidět **neúspěšná přihlášení** a odmítnuté zásahy (zamčený záznam, chybějící
  oprávnění, neplatný stav).
- U přihlášení přes access-manager i **důvod odmítnutí** (`bad_code`, `replay` …),
  který se na formulář nikdy nedostane.

Audit **nezapisuje čtení** (zobrazení záznamu, seznamy) a **nikdy nezapisuje hodnoty**:
žádná hesla, kódy, tokeny, cookies, těla požadavků ani obsah polí – jen identifikátory.

---

## Jak to funguje?

```
HTTP požadavek POST/PUT/PATCH/DELETE na /api/v1/*
    │
    ▼
AuditMiddleware (nejvnější vrstva – vidí i požadavky, které odmítne CSRF guard)
    │
    ▼
routa (může doplnit request.state.audit, např. status_from/status_to, changed)
    │
    ▼
odpověď → outcome podle HTTP stavu, chyba z těla odpovědi (max. 300 znaků)
    │
    ▼
data/audit/RRRR-MM-DD.jsonl   ← jeden řádek = jedna událost (append, O_APPEND)
```

- **Denní soubory** (`data/audit/2026-11-11.jsonl`) – retence je mazání starých souborů,
  čtení rozsahu dní je levné.
- Zápis je jediný `os.write` s `O_APPEND` – souběžné řádky se neproplétají ani bez zámku.
- Adresář `0700`, soubory `0600`.
- Selhání zápisu (plný disk) požadavek **neshodí** – zaloguje se chyba.
- Obnova vlastního zámku záznamu (heartbeat editoru každých 5 min) se nezapisuje.

---

## Rychlý start

**V aplikaci:** Admin → **Audit**. Filtry: období (výchozí posledních 7 dní),
uživatel (podřetězec), typ (přihlášení / změny), výsledek, fulltext (ID záznamu, IP…).

**Přes API:**

```bash
curl -b cookies.txt "https://uniforms.example.com/api/v1/admin/audit/?who=demo&outcome=denied&limit=50"
```

**Na disku** (nejnovější události dne):

```bash
tail -n 5 data/audit/$(date -u +%F).jsonl | python3 -m json.tool --json-lines
```

---

## Přehled událostí

### Změna záznamu

```json
{
  "t": "2026-11-11T10:27:41+00:00",
  "kind": "write",
  "op": "update_record",
  "actor": "user:demo",
  "origin": "193.0.231.250",
  "method": "PATCH",
  "path": "/api/v1/records/zoo/ZOO-2026-3922",
  "collection_id": "zoo",
  "record_id": "ZOO-2026-3922",
  "status": 200,
  "outcome": "ok",
  "status_from": "exhibit",
  "status_to": "vet",
  "changed": ["weight_kg"]
}
```

`changed` jsou **klíče** polí, tabulek a kroků checklistu, jejichž hodnota se změnila
(max. 50) – nikdy hodnoty. Automatické `last_saved` se ignoruje.

### Změna kolekce nebo šablony z Collection Designeru

```json
{
  "t": "2026-11-11T11:50:11+00:00",
  "kind": "write",
  "op": "designer_update_template",
  "actor": "user:admin",
  "origin": "193.0.231.250",
  "method": "PUT",
  "path": "/api/v1/admin/designer/collections/soc/templates/uib-bec-v2",
  "collection_id": "soc",
  "template_id": "uib-bec-v2",
  "status": 200,
  "outcome": "ok",
  "via": "designer",
  "change": "updated",
  "changed_keys": ["name", "sections"],
  "comments_discarded": 3,
  "backup": "uib_bec_v2.20261111T115010613163Z.yaml"
}
```

`op` je `designer_create_collection`, `designer_update_collection`, `designer_create_template`
nebo `designer_update_template`; `change` říká, zda soubor vznikl (`created`), změnil se
(`updated`), nebo zůstal beze změny (`unchanged`). `changed_keys` jsou **názvy** změněných
klíčů nejvyšší úrovně, nikdy hodnoty. Odmítnuté uložení nese `reject_code` (`invalid`,
`stale`, `rewrite_not_confirmed`…). Podrobnosti: [COLLECTION_DESIGNER.md](COLLECTION_DESIGNER.md#audit).

### Neúspěšné přihlášení přes access-manager

```json
{
  "t": "2026-11-11T11:48:02+00:00",
  "kind": "auth",
  "op": "login",
  "subject": "user:hana",
  "origin": "193.0.231.250",
  "method": "POST",
  "path": "/api/v1/auth/login",
  "status": 401,
  "outcome": "denied",
  "error": "Nesprávné přihlašovací údaje",
  "auth_method": "access_manager",
  "am_outcome": "denied",
  "am_reason": "bad_code"
}
```

U neúspěšného přihlášení není `actor` (nikdo přihlášen nebyl), jen `subject` – jméno,
pod kterým to někdo zkoušel. Význam `am_reason` / `reason` viz
[ACCESS_MANAGER.md – Řešení problémů](ACCESS_MANAGER.md#řešení-problémů).

### Odmítnutá změna

```json
{
  "t": "2026-11-11T11:24:10+00:00",
  "kind": "write",
  "op": "update_record",
  "actor": "user:tester",
  "collection_id": "soc",
  "record_id": "UIB-11112026-8099",
  "status": 423,
  "outcome": "denied",
  "error": "Record is locked by another user"
}
```

---

## Reference – pole události

Pole s neznámou hodnotou se **nezapisuje** (žádné prázdné řetězce ani `null`).

| Pole | ✓ | Popis |
|------|:-:|-------|
| `t` | ✓ | čas UTC, ISO-8601 s přesností na sekundy |
| `kind` | ✓ | `auth` (login / logout) \| `write` (cokoli měnícího přes API) |
| `op` | ✓ | operace = jméno API endpointu (`login`, `create_record`, `update_record`, `delete_record`, `acquire_lock`, `save_template`, `update_collection`, `create_user`, `save_config` …); u požadavku odmítnutého před routou `"METODA cesta"` |
| `actor` | | kdo to udělal – `user:<jméno>` z relace |
| `subject` | | koho se to týkalo, pokud to není aktér (jméno u přihlášení) |
| `origin` | | IP klienta (za reverzní proxy, přes `X-Forwarded-For` z nginx) |
| `method`, `path` | ✓ | HTTP metoda a cesta |
| `status` | ✓ | HTTP stav odpovědi |
| `outcome` | ✓ | `ok` (< 400) \| `denied` (401, 403, 423) \| `rejected` (ostatní 4xx) \| `error` (5xx) |
| `error` | | krátký text chyby u ne-ok výsledků |
| `collection_id`, `record_id`, `template_id`, `username` | | cíl z URL |
| `status_from`, `status_to` | | změna stavu workflow záznamu |
| `changed[]` | | klíče změněných polí záznamu, resp. názvy změněných nastavení (`save_config`) |
| `auth_method` | | `local` (heslo) \| `access_manager` (OTP) |
| `am_outcome`, `am_reason` | | verdikt access-manageru a jeho důvod |
| `reason` | | důvod odmítnutí na straně UniForms (`not_in_access_group`, `inactive`) |

---

## Konfigurace

| Klíč v `.env` | Výchozí | Popis |
|---------------|---------|-------|
| `AUDIT_DIR` | `data/audit` | adresář denních souborů (v `.gitignore`) |
| `AUDIT_RETENTION_DAYS` | `365` | starší denní soubory se smažou při založení nového dne; `0` = nemazat |

---

## Speciální témata

### Čtení a odolnost

Čtení dělí soubor **jen** na `\n` – `str.splitlines()` by dělil i na U+2028 a další
oddělovače, které zápis (`ensure_ascii=False`) v hodnotách nechává, a takový řádek by
se tiše ztratil. Poškozený nebo ručně připsaný řádek se přeskočí, zbytek dne se přečte.
API čte od nejnovějšího dne a končí po dosažení `limit`.

### Audit jako zdroj pro SIEM

Soubory jsou čisté JSON Lines – lze je posílat do SIEM běžným shipperem (Filebeat,
Vector, rsyslog imfile) přímo z `data/audit/*.jsonl`.

---

## Přehled API / modulů

| Endpoint / modul | Popis |
|------------------|-------|
| `GET /api/v1/admin/audit/` | události, nejnovější první; parametry `day_from`, `day_to` (`RRRR-MM-DD`), `who`, `kind`, `outcome`, `collection_id`, `text`, `limit` (1–5000, výchozí 500) |
| `uniforms/core/audit.py` | `append_event`, `read_events`, retence |
| `uniforms/core/audit_middleware.py` | zápis událostí pro mutující API požadavky |
| `request.state.audit` / `audit_skip` | jak routa doplní nebo potlačí svou událost |
