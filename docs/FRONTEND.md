# UniForms – Frontend a webový renderer

Tento dokument popisuje architekturu webového rozhraní UniForms od serveru přes Jinja2 šablony až po klientský JS renderer. Určeno vývojářům upravujícím frontend nebo píšícím extensions.

---

## 1. Přehled architektury

UniForms odděluje **statické HTML scaffolding** (server-side, Jinja2) od **dynamického renderování formulářů** (client-side, uniforms.js).

Jinja2 sestaví kostru stránky: navbar, sidebar, autentizaci, Bootstrap layout. Obsah formuláře — sekce záznamu — renderuje výhradně JavaScript z dat získaných přes REST API.

```
Prohlížeč
    │
    ▼
GET /records/{collection_id}/{record_id}
    │   (HTTP + JWT cookie)
    ▼
FastAPI  app/web/routes.py
    │   TemplateResponse("record_detail.html", context)
    │   → vloží do HTML: COLLECTION_ID, RECORD_ID, CURRENT_USER, IS_ADMIN, PRINT_MODE
    │   → vloží: extension_js URL seznam
    ▼
Jinja2 engine
    │   base.html  ← record_detail.html (extends)
    │   Bootstrap 5, Bootstrap Icons, DataTables, jQuery
    ▼
Kompletní HTML → Prohlížeč
    │
    │  Statické JS soubory:
    │    app/static/js/main.js      → apiFetch() helper
    │    app/static/js/uniforms.js  → UniForms renderer
    │    extensions/{id}/js/*.js    → custom renderery (extension)
    │
    ▼
JavaScript init():
    1. loadCollectionConfig()  → GET /api/v1/collections/{id}
                               → nastaví collectionConfig (title_field, workflow, ...)
    2. loadRecord()            → GET /api/v1/records/{id}/{rid}
                               → získá recordDocument (data.sections)
    3. UniForms.render(sections, container)
                               → sestaví DOM formuláře
    4. buildWorkflowUI()       → status dropdown ze workflow_states
    5. updateTakeOverButton()  → zobrazí/skryje tlačítko Převzít
    6. acquireLock()           → POST /api/v1/records/{id}/{rid}/lock
```

### Server-side vs. client-side

| Vrstva | Technologie | Co zajišťuje |
|--------|-------------|--------------|
| Server (Jinja2) | FastAPI + Jinja2 | Layout, auth, sidebar, globální terminologie, Bootstrap kostry |
| Klient (uniforms.js) | Vanilla JS | Renderování sekcí formuláře, live sync dat, locking, save |

---

## 2. URL routing

Všechny webové stránky jsou obsluhované v `app/web/routes.py`. Přihlášení se ověřuje JWT cookie `uniforms_token`.

| URL | Šablona | Vyžaduje |
|-----|---------|----------|
| `/` | přesměrování | — |
| `/login` | `login.html` | — |
| `/logout` | — (smaže cookie) | — |
| `/dashboard` | `dashboard.html` | přihlášen |
| `/records/{collection_id}` | `records.html` | přihlášen |
| `/records/{collection_id}/{record_id}` | `record_detail.html` | přihlášen |
| `/records/{collection_id}/{record_id}/print` | `record_detail.html` (`print_mode=True`) | přihlášen |
| `/templates/{collection_id}` | `templates_list.html` | přihlášen |
| `/templates/{collection_id}/new` | `template_editor.html` | `system_admin` |
| `/templates/{collection_id}/{template_id}/edit` | `template_editor.html` | `system_admin` |
| `/settings` | `settings.html` | `system_admin` |
| `/admin/users` | `admin_users.html` | `system_admin` |
| `/admin/collections` | `admin_collections.html` | `system_admin` |
| `/admin/collections/new` | `admin_collection_editor.html` | `system_admin` |
| `/admin/collections/{id}/edit` | `admin_collection_editor.html` | `system_admin` |

---

## 3. Jinja2 kontext

### Globální proměnné (dostupné ve všech šablonách)

Nastavují se jednou při startu aplikace v `app/web/routes.py`:

```python
templates.env.globals.update({
    "app_name":     uniforms.app.name,
    "app_subtitle": uniforms.app.subtitle,
    "term":         uniforms.terminology.model_dump(),
})
```

| Proměnná | Popis | Příklad |
|----------|-------|---------|
| `{{ app_name }}` | Název aplikace z `uniforms.yaml` | `UniForms` |
| `{{ app_subtitle }}` | Podtitulek z `uniforms.yaml` | `Universal Forms Engine` |
| `{{ term }}` | Dict terminologie z `uniforms.yaml → terminology` | `{"record": "ticket", ...}` |

Terminologii používáte v šablonách takto:

```html
<h1>{{ term.records | title }}</h1>         <!-- např. "Záznamy" nebo "Tickety" -->
<button>{{ term.new_record_btn }}</button>   <!-- např. "Nový záznam" -->
```

`base.html` navíc exportuje terminologii do JS objektu `TERM`, který je dostupný v každém JS souboru:

```javascript
// Přístup z JavaScriptu (definován v base.html)
TERM.record        // "záznam"
TERM.btn_save      // "Uložit"
TERM.col_status    // "Stav"
```

### Per-request kontext (liší se dle stránky)

Každý route handler předá šabloně lokální kontext:

| Proměnná | Typ | Dostupná na |
|----------|-----|-------------|
| `request` | `Request` | všude |
| `user` | `{"username": str, "role": str}` | všude (kromě login) |
| `collection_id` | `str` | stránky kolekce |
| `record_id` | `str` | detail záznamu |
| `print_mode` | `bool` | detail záznamu |
| `collection` | `CollectionConfig` | stránky kolekce (ze sidebar_ctx) |
| `accessible_collections` | `list` | všude (pro sidebar) |
| `extension_js` | `list[str]` | detail záznamu |

### Dědičnost šablon

Všechny stránky kromě `login.html` rozšiřují `base.html`:

```
base.html
├── <nav class="navbar">    (block navbar)
├── .app-shell
│   ├── <nav class="sidebar">   (block sidebar)  ← definuje každá stránka
│   └── <main class="app-main"> (block content)
└── (block scripts)
```

`login.html` je samostatná — nepoužívá `base.html`.

### Layout (app-shell pattern)

Aplikace fixuje layout tak, aby sidebar a hlavní obsah scrollovaly nezávisle:

```
<body>                           display: flex; flex-direction: column; height: 100%
  <nav class="navbar">           přirozená výška
  <div class="app-shell">        flex: 1; min-height: 0
    <nav class="sidebar">        flex-shrink: 0; overflow-y: auto
    <main class="app-main">      flex: 1; overflow-y: auto
```

> **Poznámka:** `min-height: 0` je kritické — bez něj flex položky ignorují `overflow-y` a obsah přetéká viewport.

---

## 4. Stránka seznamu záznamů (`records.html`)

Záznamy se načítají asynchronně přes `GET /api/v1/records/{collection_id}/` a renderují se jako DataTable.

### Tok dat

```
DOMContentLoaded
    │
    ▼
apiFetch("/api/v1/records/{collection_id}/")
    │   vrátí pole recordů
    ▼
DataTable.rows.add(records)
    │   sloupce: Vytvořeno | Stav | ID | Název | Šablona | Řešitel | Zámek | Skrytá priorita | Akce
    ▼
Render tabulky
```

### Sloupce DataTable

| Index | Sloupec | Zdroj dat |
|-------|---------|-----------|
| 0 | Vytvořeno | `record.created_at` |
| 1 | Stav | `record.status` — badge |
| 2 | ID záznamu | `record.id` |
| 3 | Název | `getFieldValue(record, title_field)` |
| 4 | Šablona | `record.template_name` |
| 5 | Řešitel | `getFieldValue(record, "coordinator")` |
| 6 | Zámek | `record.locked_by` |
| 7 | *(skrytý)* | priorita stavu pro řazení (1–N) |
| 8 | Akce | Tisk, Otevřít; admin: Odemknout, Smazat |

`getFieldValue(record, key)` prohledává všechny sekce záznamu a vrátí první nalezenou hodnotu pole s daným klíčem.

### Řazení a filtrování

Primární řazení: sloupec 7 (priorita stavu) ASC — aktivní záznamy nahoře.
Sekundární řazení: sloupec 0 (datum) DESC — nejnovější první v rámci stavu.

Tlačítka filtrů nad tabulkou volají `dt.column(1).search(regex)` — filtrují sloupec Stav regulárním výrazem `^Label$`.

---

## 5. Stránka detailu záznamu (`record_detail.html`)

Nejsložitější stránka aplikace. Načítá kolekci i záznam, renderuje formulář, spravuje editační zámky a zajišťuje ukládání.

### Globální JS proměnné (vložené serverem)

```javascript
const COLLECTION_ID = '{{ collection_id }}';
const RECORD_ID     = '{{ record_id }}';
const CURRENT_USER  = '{{ user.username }}';
const IS_ADMIN      = {{ 'true' if user.role == 'system_admin' else 'false' }};
const PRINT_MODE    = {{ 'true' if print_mode else 'false' }};
```

### Životní cyklus stránky

```
DOMContentLoaded
    │
    ▼
init()
    │
    ├─► loadCollectionConfig()
    │       GET /api/v1/collections/{COLLECTION_ID}
    │       → collectionConfig (title_field, workflow_states, take_over, ...)
    │
    ├─► loadRecord()
    │       GET /api/v1/records/{COLLECTION_ID}/{RECORD_ID}
    │       → recordDocument (data.sections)
    │       → UniForms.render(sections, container)
    │       → buildWorkflowUI(workflowStates)
    │       → updateTakeOverButton(record)
    │
    ├─► loadFilePath()        (jen pokud není PRINT_MODE)
    │       GET /api/v1/records/{id}/{rid}/path → zobrazí cestu k souboru
    │
    └─► acquireLock()         (jen pokud není PRINT_MODE)
            POST /api/v1/records/{id}/{rid}/lock
            → 200: formulář editovatelný
            → 423: formulář read-only, banner "Edituje {locked_by}"
```

### Klíčové funkce stránky

| Funkce | Popis |
|--------|-------|
| `findFieldInRecord(r, key)` | Hledá pole v záznamu; prochází i `section_group` podsekce |
| `getRecordTitle(r)` | Vrátí hodnotu pole `collectionConfig.title_field` |
| `updateTakeOverButton(r)` | Zobrazí tlačítko jen pokud `take_over.field` existuje v záznamu |
| `takeover()` | Zapíše username + timestamp do `take_over.field`; okamžitě uloží |
| `acquireLock()` | `POST /lock` — získá editační zámek |
| `releaseLock()` | `DELETE /lock` — uvolní editační zámek |
| `saveRecord()` | `PATCH /api/v1/records/{id}/{rid}` s aktuálními daty |
| `changeStatus(newStatus)` | `PATCH` se změnou pole `status`; spouští okamžité uložení |
| `buildWorkflowUI(states)` | Sestaví status dropdown ze stavů workflow |

### Uložení záznamu

```
Tlačítko "Uložit":
    saveRecord()  →  PATCH /api/v1/records/{id}/{rid}
    Zámek zůstane. Uživatel zůstává na stránce.

Tlačítko "Uložit a zavřít":
    saveRecord()  →  releaseLock()  →  přesměrování na seznam záznamů

Změna stavu (select):
    changeStatus()  →  okamžité PATCH na pozadí (bez kliknutí Uložit)

Zavření záložky / navigace pryč (beforeunload):
    releaseLock()   →  DELETE /lock  (best-effort)
```

---

## 6. Editační zámky (locking)

Zámky zabraňují konfliktním editacím. Každý záznam může mít nejvýše jeden aktivní zámek.

```
Otevření záznamu:
    POST /api/v1/records/{id}/{rid}/lock
         │
         ├─► 200 OK
         │      Zámek získán. Formulář je editovatelný.
         │
         └─► 423 Locked  { locked_by: "jana", locked_at: "..." }
                Banner: "Záznam edituje jana"
                Formulář: setReadOnly(true) → read-only mode

Zavření záznamu:
    DELETE /api/v1/records/{id}/{rid}/lock
```

| Stav | Formulář | Banner |
|------|----------|--------|
| Záznam volný | editovatelný | — |
| Zamčeno mnou | editovatelný | info o zámku |
| Zamčeno jiným | read-only | "Edituje {locked_by}" |

`system_admin` může vynutit uvolnění cizího zámku tlačítkem **Force unlock** ve správě záznamů.

---

## 7. Tisková verze (`/print`)

URL `/records/{coll_id}/{rec_id}/print` otevře `record_detail.html` s `print_mode=True`.

V tiskovém režimu:
- Skryje navbar, sidebar, toolbar a akční tlačítka
- Rozbalí všechny accordion sekce (žádná není sbalena)
- Odstraní help texty, placeholdery a hint boxy
- Přepne formulář do read-only (`setReadOnly(true)`)
- Zobrazí tlačítko **Print / Save PDF** → `window.print()`
- Nezíská editační zámek (locking je vynechán)

---

## 8. uniforms.js API

`uniforms.js` je zabalen v IIFE. Vystavuje jeden globální objekt `UniForms`. Žádné interní funkce nejsou viditelné zvenčí.

### `UniForms.render(sections, container)`

Hlavní vstupní bod. Vymaže obsah `container` a vykreslí všechny sekce jako Bootstrap 5 accordion.

```javascript
UniForms.render(
    recordDocument.data.sections,
    document.getElementById('sections-container')
);
```

Po vykreslení jsou všechny inputy živě napojeny na data objektu — změna pole automaticky zapíše `field.value = input.value`. Při ukládání stačí serializovat JS objekt; není potřeba číst DOM.

### `UniForms.registerRenderer(type, fn)`

Zaregistruje custom renderer pro nový typ sekce. Renderer přijme objekt sekce a vrátí DOM element (nebo `null`).

```javascript
UniForms.registerRenderer('muj_typ', function(section) {
    const { el, setHTML } = UniForms._helpers;
    const wrap = el('div', 'p-3');
    setHTML(wrap, section.title || '');
    return wrap;
});
```

Volá se z extension JS souborů po načtení `uniforms.js`.

### `UniForms.setReadOnly(readonly)`

Přepne všechny inputy formuláře na read-only nebo editovatelné.

```javascript
UniForms.setReadOnly(true);   // read-only (zamčený záznam, tiskový režim)
UniForms.setReadOnly(false);  // editovatelné
```

### `UniForms._helpers` — pomocné funkce

Interní utility dostupné pro extension renderery:

| Funkce | Popis |
|--------|-------|
| `el(tag, css?, html?)` | Vytvoří DOM element s třídou; `html` prochází sanitizací |
| `setHTML(element, html)` | Bezpečné `innerHTML` — vždy sanitizuje |
| `sanitizeHTML(html)` | XSS sanitizace přes `DOMParser` |
| `renderFieldRow(field)` | Label + input řádek pro jedno pole |
| `renderFieldInput(field)` | Input / select / textarea widget |
| `renderForm(fields)` | Sestaví seznam `fieldRow` elementů |
| `renderInfoGrid(fields)` | Kompaktní read-only info mřížka (pro `header` sekce) |
| `buildTableHead(cols, lbls)` | `<thead>` pro tabulku |
| `buildOptions(select, opts, value)` | Naplní `<select>` options a nastaví vybranou hodnotu |
| `makeDeleteBtn(onClick)` | Tlačítko smazání řádku tabulky |
| `normalizeColumns(section)` | v1 → v2 normalizace definice sloupců |
| `evalExpr(expr, fields)` | Vyhodnotí `visible_if` / `required_if` výraz |
| `applyConditionals(fields, container)` | Naváže `visible_if` / `required_if` na DOM události |

> **Poznámka:** `_helpers` jsou interní API. Mohou se měnit mezi verzemi. Kde je to možné, stavte renderer na standardních DOM API.

### Bezpečnost (XSS ochrana)

Veškerý HTML obsah z JSON (labely, nadpisy, hinty, texty kroků) prochází `sanitizeHTML()`:
- Parsuje HTML v izolovaném `DOMParser` dokumentu — skripty se nespustí
- Odstraní: `<script>`, `<iframe>`, `<object>`, `<embed>`, `<link>`, `<meta>`
- Odstraní všechny `on*` atributy a `href="javascript:"`

Hodnoty zadávané uživatelem (inputy, textarey) **nikdy nevstoupí do `innerHTML`** — čtou a zapisují se přes `.value`.

> **Pozor:** Přímé `element.innerHTML = ...` je zakázáno. Vždy použij `setHTML()` nebo `el()`.

---

## 9. Extension systém

Extensions mohou registrovat vlastní typy sekcí bez modifikace `uniforms.js`.

### Jak extension funguje

```
extensions/{ext_id}/
    extension.yaml     → manifest (id, name, js, templates_dir, ...)
    js/
        renderer.js    → registruje custom renderery
    templates/
        *.yaml         → YAML šablony specifické pro extension
```

Extension JS soubory se načtou po `uniforms.js` — jejich URL jsou vloženy serverem do `record_detail.html` přes proměnnou `extension_js`.

### Registrace vlastního rendereru

```javascript
// extensions/soc/js/soc_renderer.js

UniForms.registerRenderer('ioc_table', function renderIocTable(section) {
    const { el, buildTableHead, makeDeleteBtn } = UniForms._helpers;

    const wrap = el('div', 'table-responsive');
    const table = el('table', 'table table-sm table-bordered');

    // Záhlaví
    table.appendChild(buildTableHead(
        ['indicator', 'type', 'note'],
        ['Indikátor', 'Typ', 'Poznámka']
    ));

    // Tělo tabulky
    const tbody = el('tbody');
    (section.rows || []).forEach(row => {
        const tr = el('tr');
        ['indicator', 'type', 'note'].forEach(key => {
            const td = el('td');
            const inp = el('input', 'form-control form-control-sm');
            inp.value = row[key] || '';
            inp.addEventListener('change', () => { row[key] = inp.value; });
            td.appendChild(inp);
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);

    return wrap;
});
```

Šablona pak použije:

```yaml
- id: ioc_seznam
  type: ioc_table
  title: Indikátory kompromitace
  rows: []
```

> **Tip:** Extension renderer dostane celý objekt sekce — `section.rows`, `section.columns`, `section.title`, `section.hint` atd. Data zapisuj přímo zpět do sekce (mutace objektu) — `saveRecord()` serializuje celý JS objekt.

---

## 10. Přehled veřejného API uniforms.js

| Funkce | Podpis | Popis |
|--------|--------|-------|
| `UniForms.render` | `(sections, container)` | Vykreslí pole sekcí do DOM kontejneru |
| `UniForms.registerRenderer` | `(type, fn)` | Zaregistruje custom renderer pro nový typ sekce |
| `UniForms.setReadOnly` | `(readonly)` | Přepne všechny inputy na read-only nebo editovatelné |
| `UniForms._helpers` | objekt | Interní utility pro extension renderery |

### Vestavěné renderery (přepsatelné přes `registerRenderer`)

| Typy sekcí | Interní renderer |
|------------|-----------------|
| `header`, `workbook_header`, `playbook_header`, `record_header` | `renderHeader` |
| `form` | `renderFormSection` |
| `checklist` | `renderChecklist` |
| `table` | `renderTable` |
| `section_group` | `renderSectionGroup` |
| `contact_table` | `renderContactTable` |
| `item_table`, `assets_table` | `renderItemTable` |
| `task_table`, `action_table` | `renderTaskTable` |

### Klíčové JS funkce na stránce detailu záznamu

| Funkce | Popis |
|--------|-------|
| `init()` | Spustí celý životní cyklus stránky |
| `loadCollectionConfig()` | `GET /api/v1/collections/{id}` → collectionConfig |
| `loadRecord()` | `GET /api/v1/records/{id}/{rid}` → renderuje formulář |
| `saveRecord()` | `PATCH` záznam s aktuálními daty |
| `changeStatus(s)` | Okamžité `PATCH` při změně stavu |
| `acquireLock()` | `POST /lock` |
| `releaseLock()` | `DELETE /lock` |
| `takeover()` | Zapíše uživatele do `take_over.field` + uloží |
| `findFieldInRecord(r, key)` | Hledá pole v záznamu přes všechny sekce |
| `getRecordTitle(r)` | Vrátí hodnotu `title_field` záznamu |
| `updateTakeOverButton(r)` | Zobrazí/skryje tlačítko Převzít |
| `buildWorkflowUI(states)` | Sestaví status dropdown |

---

## Reference

- Renderer sekcí (podrobný popis typů a polí): [UNIFORMS_JS.md](UNIFORMS_JS.md)
- REST API: [API.md](API.md)
- Pipeline šablony (jak YAML → data sekce): [TEMPLATE_PIPELINE.md](TEMPLATE_PIPELINE.md)
- Psaní šablon: [TEMPLATE_AUTHORING.md](TEMPLATE_AUTHORING.md)
