# UniForms – Webová vrstva a renderování

Tento dokument popisuje, jak webová vrstva aplikace funguje: jak FastAPI a Jinja2 sestavují HTML stránky, jaké proměnné jsou dostupné ve všech šablonách, jak JavaScript načítá data z REST API a jak se záznamy renderují do formulářů.

Určeno vývojářům upravujícím nebo rozšiřujícím frontend.

---

## Jak to funguje?

```
Prohlížeč
    │  GET /records/soc  (HTTP + Cookie)
    ▼
FastAPI – app/web/routes.py
    │  TemplateResponse("records.html", context)
    ▼
Jinja2 engine
    │  base.html ← records.html (extends)
    ▼
Kompletní HTML → Prohlížeč
    │
    │  JS: fetch /api/v1/records/soc/ → DataTables, apiFetch helpery
    │  JS: UniForms.render(sections, container) → interaktivní formulář
    ▼
REST API (app/api/v1/)
```

Server posílá kompletní HTML — JavaScript zajišťuje dynamické operace (DataTables, volání API, renderování formulářů přes `uniforms.js`).

---

## Přehled souborů

| Soubor | Role |
|--------|------|
| `app/web/routes.py` | FastAPI router pro webové stránky — vrací `TemplateResponse` |
| `app/templates/base.html` | Základní layout (navbar + app-shell) |
| `app/templates/login.html` | Přihlašovací stránka (samostatná, nerozšiřuje `base.html`) |
| `app/templates/dashboard.html` | Nástěnka |
| `app/templates/records.html` | Seznam záznamů (DataTables + filtry) |
| `app/templates/record_detail.html` | Detail / editace záznamu |
| `app/templates/templates_list.html` | Seznam šablon |
| `app/templates/template_editor.html` | Editor YAML šablony (Ace Editor) |
| `app/templates/settings.html` | Nastavení aplikace (admin) |
| `app/templates/admin_users.html` | Správa uživatelů (admin) |
| `app/static/js/main.js` | Globální JS helper (`apiFetch`) |
| `app/static/js/uniforms.js` | Renderer sekcí formuláře |
| `app/static/css/custom.css` | CSS (app-shell layout, sidebar, filtry) |

---

## Dědičnost Jinja2 šablon

Všechny stránky (kromě `login.html`) rozšiřují `base.html`:

```
base.html
├── navbar (block navbar)
├── .app-shell
│   ├── sidebar (block sidebar)  ← definuje každá potomková šablona
│   └── .app-main (block content)
└── scripts (block scripts)
```

`login.html` je samostatná stránka — nepoužívá `base.html`.

---

## Jinja2 globály

Proměnné dostupné automaticky ve **všech** šablonách bez explicitního předání v každém route handleru:

| Proměnná | Zdroj | Příklad hodnoty |
|----------|-------|-----------------|
| `{{ app_name }}` | `config.py` → `uniforms.yaml` / SQLite | `UniForms` |
| `{{ app_version }}` | `config.py` → `.env` `APP_VERSION` | `1.0.0` |
| `{{ app_subtitle }}` | `config.py` → `uniforms.yaml` / SQLite | `IT Helpdesk Portal` |
| `{{ term }}` | `config.py` → `uniforms.yaml` sekce `terminology` | `{"record": "ticket", "records": "tickets", ...}` |

Nastavení v `app/web/routes.py` při startu aplikace:

```python
templates.env.globals.update({
    "app_name":     app_settings.app_name,
    "app_version":  app_settings.app_version,
    "app_subtitle": app_settings.app_subtitle,
    "term":         app_settings.terminology,
})
```

Klíče z `term` slouží k použití doménové terminologie v šablonách bez hardkódování:

```html
<!-- V libovolné Jinja2 šabloně -->
<h1>{{ term.records | title }}</h1>         <!-- např. "Tickety" -->
<button>{{ term.new_record_btn }}</button>   <!-- např. "Nový ticket" -->
```

Hodnoty jsou uloženy v SQLite při prvním spuštění (`init_db`) a lze je změnit přes `PATCH /api/v1/settings/`. Změny v GUI se projeví okamžitě v API odpovědích; v Jinja2 šablonách až po restartu serveru (globály se nastavují jednou při startu).

### Proměnné předávané v každém požadavku

Každý webový route handler předá lokální kontext šabloně:

| Proměnná | Typ | Popis |
|----------|-----|-------|
| `user` | `dict` (`username`, `role`) | Přihlášený uživatel; `None` na přihlašovací stránce |
| `collection_id` | `str` | ID aktuální kolekce (stránky se záznamy a šablonami) |
| `record_id` | `str` | ID záznamu (pouze `record_detail.html`) |
| `settings` | `dict[str, str]` | Aktuální nastavení z SQLite (pouze `settings.html`) |
| `print_mode` | `bool` | Tiskový režim (pouze detail záznamu přes `/print`) |

### JavaScript globál `TERM`

`base.html` vystavuje terminologické hodnoty jako JavaScript objekt `TERM`, aby je mohl používat i JS-generovaný HTML (DataTables buňky, dynamické tlačítka):

```html
<script>
const TERM = {
    record:        "{{ term.record }}",
    records:       "{{ term.records }}",
    btn_cancel:    "{{ term.btn_cancel }}",
    btn_delete:    "{{ term.btn_delete }}",
    btn_edit:      "{{ term.btn_edit }}",
    btn_clone:     "{{ term.btn_clone }}",
    btn_print:     "{{ term.btn_print }}",
    btn_open:      "{{ term.btn_open }}",
    btn_save:      "{{ term.btn_save }}",
    btn_create:    "{{ term.btn_create }}",
    col_status:    "{{ term.col_status }}",
    col_title:     "{{ term.col_title }}",
    col_lock:      "{{ term.col_lock }}",
    filter_all:    "{{ term.filter_all }}",
    coordinator_label: "{{ term.coordinator_label }}",
    record_id_label:   "{{ term.record_id_label }}",
};
</script>
```

---

## Layout (app-shell pattern)

Aplikace používá **app-shell pattern** pro fixní layout bez překrytí sidebaru a obsahu:

```
<body>                          ← d-flex flex-column, height: 100%
  <nav class="navbar">          ← přirozená výška, nescrolluje
  <div class="app-shell">       ← flex: 1, min-height: 0 (zbývající výška viewportu)
    <nav class="sidebar">       ← flex-shrink: 0, overflow-y: auto
    <main class="app-main">     ← flex: 1, overflow-y: auto (obsah scrolluje)
```

Klíčové CSS vlastnosti (`custom.css`):

```css
html, body { height: 100%; overflow: hidden; display: flex; flex-direction: column; }
.app-shell  { display: flex; flex: 1; min-height: 0; overflow: hidden; }
.sidebar    { flex-shrink: 0; overflow-y: auto; }
.app-main   { flex: 1; min-width: 0; min-height: 0; overflow-y: auto; }
```

`min-height: 0` je kritické — bez něj flex položky ignorují `overflow-y` a neomezují svou výšku, čímž stránka přesahuje viewport.

---

## Seznam záznamů — `records.html`

Stránka načítá záznamy asynchronně přes `GET /api/v1/records/{collection_id}/` a renderuje je pomocí DataTables.

### Pořadí sloupců

| Index | Sloupec | Popis |
|-------|---------|-------|
| 0 | Vytvořeno | Datum a čas vytvoření (`created_at`) |
| 1 | Stav | Badge s hodnotou stavu |
| 2 | ID | ID záznamu (např. `SOC-202603-0042`) |
| 3 | Název | Hodnota pole `title` z hlavičky záznamu |
| 4 | Šablona | Název šablony |
| 5 | Řešitel | Hodnota pole `coordinator` z hlavičky záznamu |
| 6 | Zámek | Kdo má záznam otevřen (`locked_by`) |
| 7 | *(skrytý)* | Priorita řazení stavu (1–N) |
| 8 | Akce | Tisknout, Otevřít; admin: Odemknout / Smazat |

### Řazení

Primární: sloupec 7 (priorita stavu) ASC — aktivní záznamy nahoře.
Sekundární: sloupec 0 (datum) DESC — nejnovější první v rámci stejného stavu.

### Filtry

Tlačítka nad tabulkou volají `dt.column(1).search(regex)` — filtrují sloupec 1 (Stav) pomocí regulárního výrazu `^Label$`.

---

## Detail záznamu — `record_detail.html`

Stránka načte záznam přes `GET /api/v1/records/{collection_id}/{record_id}` a renderuje sekce formuláře pomocí `UniForms.render()`.

### Zámky a read-only režim

| Stav | Chování |
|------|---------|
| Záznam odemčen | Stránka automaticky požádá o zámek (`POST /lock`) |
| Zamčeno mnou | Formulář je editovatelný; banner zobrazuje info o zámku |
| Zamčeno jiným uživatelem | Formulář je read-only (`setReadOnly(true)`) |

**Uložit** — uloží data, zámek zůstane (uživatel zůstává na stránce).

**Uložit a zavřít** — uloží data, uvolní zámek (`DELETE /lock`), přesměruje na seznam záznamů.

### Automatické uložení

Změna pole `status` (výběr stavu) spouští okamžité uložení na pozadí přes `PATCH /api/v1/records/{collection_id}/{record_id}` — bez nutnosti kliknout na Uložit.

### Renderování formuláře

```javascript
// Zavolá se po načtení záznamu z API
const recordData = await apiFetch(`/api/v1/records/${collectionId}/${recordId}`);
UniForms.render(recordData.data.sections, document.getElementById('form-container'));
```

Po renderování jsou `recordData.data.sections[*].fields[*].value` vždy aktuální, jak analytik edituje pole.

---

## Statické soubory

```
app/static/
├── css/
│   └── custom.css          — vlastní styly (app-shell, sidebar, filtry, badges)
├── js/
│   ├── main.js             — apiFetch() helper (přidá cookie + X-Requested-With)
│   └── uniforms.js         — renderer sekcí formuláře
└── vendor/                 — staženo skriptem scripts/download_vendors.py
    ├── bootstrap/
    ├── bootstrap-icons/
    ├── jquery/
    ├── datatables/
    └── ace/                — Ace Editor (template_editor.html)
```

---

## Přehled URL a šablon

| URL | Šablona | Auth |
|-----|---------|------|
| `/` | — | přesměrování na `/dashboard` nebo `/login` |
| `/login` | `login.html` | — |
| `/logout` | — | — (smaže cookie) |
| `/dashboard` | `dashboard.html` | vyžadována |
| `/records/{collection_id}` | `records.html` | vyžadována |
| `/records/{collection_id}/{record_id}` | `record_detail.html` | vyžadována |
| `/records/{collection_id}/{record_id}/print` | `record_detail.html` (`print_mode=True`) | vyžadována |
| `/templates/{collection_id}` | `templates_list.html` | vyžadována |
| `/templates/{collection_id}/new` | `template_editor.html` | collection admin |
| `/templates/{collection_id}/{id}/edit` | `template_editor.html` | collection admin |
| `/settings` | `settings.html` | admin |
| `/admin/users` | `admin_users.html` | admin |

---

## Reference

- Renderer sekcí formuláře: [UNIFORMS_JS.md](UNIFORMS_JS.md)
- REST API: [API.md](API.md)
- Pipeline šablony: [TEMPLATE_PIPELINE.md](TEMPLATE_PIPELINE.md)
