# uniforms.js — Průvodce pro vývojáře

`uniforms.js` je klientský renderer formulářů pro UniForms. Přijme pole sekcí v JSON formátu a DOM element; vykreslí interaktivní HTML formulář přímo v prohlížeči bez server-side šablonování.

Určeno pro: vývojáře píšící extensions a vývojáře integrující renderer do vlastních stránek.

**Závislosti:** Bootstrap 5 (CSS + JS bundle, pro accordion), Bootstrap Icons. Žádné jiné knihovny.

---

## Jak to funguje?

```
JSON dokument (pole sekcí z REST API)
        │
        ▼
UniForms.render(sections, container)
        │  pro každou sekci zavolá příslušnou render* funkci podle section.type
        ▼
DOM elementy (karty, tabulky, inputy, checkboxy...)
        │
        ▼
Analytik edituje pole → handler okamžitě zapíše zpět do JS objektu
        │                 field.value = input.value
        ▼
Na uložení: JSON.stringify(doc) → PATCH /api/v1/records/{id}
```

Formulář a datový objekt jsou vždy synchronizovány. Neexistuje žádný krok „přečti formulář při odeslání" — data jsou živá v objektu od okamžiku, kdy analytik změní pole.

---

## Rychlý start

Minimální HTML stránka, která vykreslí formulář z JSON:

```html
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <title>UniForms – test</title>
    <link rel="stylesheet" href="vendor/bootstrap/css/bootstrap.min.css">
    <link rel="stylesheet" href="vendor/bootstrap-icons/bootstrap-icons.min.css">
</head>
<body class="container py-4">

    <div id="form-container"></div>
    <button id="save-btn" class="btn btn-primary mt-3">Ulozit</button>

    <script src="vendor/bootstrap/js/bootstrap.bundle.min.js"></script>
    <script src="uniforms.js"></script>
    <script>
        // Dokument pochází z API — zde simulujeme jednoduchý příklad
        const doc = {
            sections: [
                {
                    id: "zakladni_info",
                    type: "form",
                    title: "Zakladni informace",
                    fields: [
                        { key: "nazev",    label: "Nazev",    type: "text",     editable: true, value: null, example: "Strucny popis pozadavku" },
                        { key: "priorita", label: "Priorita", type: "select",   editable: true, value: null, options: ["kriticka", "vysoka", "stredni", "nizka"] },
                        { key: "poznamka", label: "Poznamka", type: "textarea", editable: true, value: null }
                    ]
                }
            ]
        };

        // Vykreslení formuláře
        UniForms.render(doc.sections, document.getElementById('form-container'));

        // Po vyplnění polí analytiker: doc.sections[*].fields[*].value obsahuje aktuální data
        document.getElementById('save-btn').addEventListener('click', () => {
            console.log(JSON.stringify(doc, null, 2));
            // fetch('/api/v1/records/REC-202603-0001', {
            //   method: 'PATCH',
            //   headers: { 'Content-Type': 'application/json' },
            //   body: JSON.stringify({ data: doc })
            // });
        });
    </script>
</body>
</html>
```

Po načtení stránky se zobrazí Bootstrap karta s nadpisem „Zakladni informace" a třemi poli. Pole „Nazev" bude mít šedý placeholder „Strucny popis pozadavku". Po kliknutí na „Ulozit" se objekt `doc` vypíše do konzole — `doc.sections[0].fields[0].value` obsahuje text zadaný analytikem.

---

## Přehled typů sekcí

| Typ | Kdy použít |
|-----|-----------|
| `header` | První sekce záznamu — zobrazovaný název, auto-vyplněná metadata (ID, šablona, čas) |
| `form` | Obecný formulář s poli — text, výběr, datum, textarea |
| `checklist` | Procedurální průvodce — kroky s checkboxem a poznámkou analytika |
| `table` | Univerzální tabulka v2 — per-sloupec typ, options a editovatelnost |
| `section_group` | Bootstrap accordion seskupující více subssekcí |

Starší typy (`workbook_header`, `playbook_header`, `record_header`, `contact_table`, `item_table`, `assets_table`, `task_table`, `action_table`) jsou zachovány jako aliasy pro zpětnou kompatibilitu existujících šablon.

---

## Detaily typů sekcí

### Hlavicka (`header`)

Speciální varianta formuláře určená jako první sekce každého záznamu. Editovatelná pole se zobrazí prominentně nahoře; pole pouze pro čtení (např. `record_id`, verze šablony) jsou vykreslena kompaktně jako info-grid pod oddělovačem.

Aliasy: `workbook_header`, `playbook_header`, `record_header` se vykreslí identicky.

```json
{
  "id": "hlavicka",
  "type": "header",
  "title": "Zakladni informace o pozadavku",
  "fields": [
    { "key": "nazev",         "label": "Nazev",        "type": "textarea", "editable": true,  "value": null, "example": "Strucny popis" },
    { "key": "resitel",       "label": "Resitel",      "type": "text",     "editable": true,  "value": null },
    { "key": "record_id",     "label": "ID zaznamu",   "type": "text",     "editable": false, "value": null, "auto_value": "record_id" },
    { "key": "sablona",       "label": "Sablona",      "type": "text",     "editable": false, "value": null, "auto_value": "template_name" },
    { "key": "posledni_uloz", "label": "Posledni uloz","type": "text",     "editable": false, "value": null, "auto_value": "last_saved" }
  ]
}
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní identifikátor sekce |
| `type` | ✓ | `"header"` (aliasy: `workbook_header`, `playbook_header`, `record_header`) |
| `title` | ✓ | Nadpis karty |
| `fields[]` | ✓ | Editovatelná pole zobrazena prominentně; `editable: false` jako info-grid |
| `description` | | Podnadpis v záhlaví karty (pravá strana) |

---

### Formulář (`form`)

Nejjednodušší sekce. Pole jsou zobrazena jako dvousloupcový grid — label vlevo, input vpravo. Volitelný klíč `hint` zobrazí modrý informační box nad formulářem.

Podporuje podmíněnou viditelnost (`visible_if`) a podmíněnou povinnost (`required_if`) na úrovni jednotlivých polí.

```json
{
  "id": "uzavreni",
  "type": "form",
  "title": "Uzavreni pozadavku",
  "hint": "Pred uzavrenim oveřte, ze zadatel byl informovan o vysledku.",
  "fields": [
    {
      "key": "priorita",
      "label": "Priorita",
      "type": "select",
      "editable": true,
      "value": null,
      "options": ["kriticka", "vysoka", "stredni", "nizka"]
    },
    {
      "key": "eskalace",
      "label": "Duvod eskalace",
      "type": "textarea",
      "editable": true,
      "value": null,
      "visible_if": "priorita == 'kriticka' || priorita == 'vysoka'",
      "placeholder": "Popiste duvod eskalace..."
    },
    {
      "key": "reseni",
      "label": "Reseni",
      "type": "textarea",
      "editable": true,
      "value": null,
      "required_if": "priorita != null"
    },
    {
      "key": "uzavreno",
      "label": "Datum uzavreni",
      "type": "datetime",
      "editable": true,
      "value": null
    }
  ]
}
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní identifikátor sekce |
| `type` | ✓ | `"form"` |
| `title` | ✓ | Nadpis karty |
| `fields[]` | ✓ | Formulářová pole — viz tabulka typů polí níže |
| `description` | | Podnadpis v záhlaví karty (pravá strana) |
| `hint` | | HTML text vykreslený jako modrý informační box nad formulářem |
| `note` | | Metadata uložená v datech; zobrazí je `section_group` accordion |

---

### Checklist (`checklist`)

Procedurální průvodce. Kroky jsou organizovány do pojmenovaných skupin. Každý krok má checkbox, pole pro poznámku analytika, volitelné hinty (šedé boxy) a volitelný blok výsledku na konci skupiny.

```json
{
  "id": "vysetrovani",
  "type": "checklist",
  "title": "Postup vysetrovani",
  "step_groups": [
    {
      "id": "uvodni_triage",
      "title": "1. Uvodni triage",
      "note": "cil: 15 minut",
      "hints": ["Zkontrolujte systemove logy pred pokracovanim."],
      "steps": [
        {
          "id": "s01",
          "action": "Potvrdte, ze problem je reprodukovatelny.",
          "example": "Reprodukovano na Windows 11 build 22631 — postihuje pouze prihlasovaci obrazovku",
          "done": false,
          "analyst_note": null
        },
        {
          "id": "s02",
          "action": "Identifikujte postizene uzivatele nebo sluzby.",
          "done": false,
          "analyst_note": null
        }
      ]
    }
  ],
  "result": {
    "title": "Vysledek triage",
    "notifications": [
      { "condition": "Potvrzena hardwarova zavada", "actions": ["Eskalujte na HW tym", "Vytvorte pozadavek na vymenu"] }
    ],
    "fields": [
      {
        "key": "verdict",
        "label": "Verdict",
        "type": "select",
        "editable": true,
        "value": null,
        "options": ["Hardwarova zavada", "Softwarova zavada", "Chyba uzivatele", "Nelze reprodukovat"]
      }
    ]
  }
}
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní identifikátor sekce |
| `type` | ✓ | `"checklist"` |
| `title` | ✓ | Nadpis karty |
| `step_groups[]` | ✓ | Skupiny kroků |
| `step_groups[].id` | ✓ | Identifikátor skupiny |
| `step_groups[].title` | ✓ | Nadpis skupiny (může být `null` pro flat kroky generované backendem) |
| `step_groups[].steps[]` | ✓ | Kroky ve skupině |
| `steps[].id` | ✓ | Identifikátor kroku |
| `steps[].action` | ✓ | Text instrukce kroku (HTML-sanitizovaný) |
| `steps[].done` | ✓ | Počáteční stav checkboxu — v šabloně vždy `false` |
| `steps[].analyst_note` | ✓ | Počáteční hodnota poznámky — v šabloně vždy `null` |
| `description` | | Podnadpis v záhlaví karty |
| `step_groups[].note` | | Šedý text za nadpisem skupiny |
| `step_groups[].hints[]` | | Šedé informační boxy (provozní hinty) |
| `steps[].example` | | Placeholder v textarea poznámky; `is_example: true` → vyčistí se při klonování |
| `result{}` | | Blok výsledku na konci checklistu |
| `result.title` | ◐ | Povinný pokud je `result` definován |
| `result.fields[]` | ◐ | Formulářová pole bloku výsledku |
| `result.notifications[]` | | Oznamovací pokyny — `string[]` nebo `[{ condition, actions[] }]` |

---

### Tabulka (`table`)

Univerzální tabulka v2 s per-sloupec konfigurací. Každý sloupec je definován jako dict s `key`, `label`, `type`, `options` a `editable`. Analytik může přidávat (`allow_append`) a mazat (`allow_delete`) řádky.

```json
{
  "id": "dotcene_systemy",
  "type": "table",
  "title": "Dotcene systemy",
  "columns": [
    { "key": "nazev",    "label": "Nazev systemu", "type": "text",   "editable": true },
    { "key": "typ",      "label": "Typ",           "type": "select", "editable": true, "options": ["Server", "Stanice", "Ucet", "Aplikace"] },
    { "key": "vlastnik", "label": "Vlastnik",      "type": "text",   "editable": true },
    { "key": "poznamka", "label": "Poznamka",      "type": "text",   "editable": true }
  ],
  "allow_append": true,
  "allow_delete": true,
  "rows": [
    { "nazev": "mail.example.com", "typ": "Server", "vlastnik": "IT Ops", "poznamka": null }
  ]
}
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní identifikátor sekce |
| `type` | ✓ | `"table"` |
| `title` | ✓ | Nadpis karty |
| `columns[]` | ✓ | Definice sloupců jako list dictů |
| `columns[].key` | ✓ | Klíč sloupce v řádku |
| `columns[].label` | ✓ | Záhlaví sloupce |
| `columns[].type` | ✓ | Typ inputu: `text`, `select`, `datetime` |
| `columns[].editable` | ✓ | `true` → sloupec je editovatelný |
| `rows[]` | ✓ | Řádky tabulky (může být prázdné `[]`) |
| `description` | | Podnadpis v záhlaví karty |
| `columns[].options[]` | ◐ | Povinné pokud `type: "select"` — list hodnot výběru |
| `allow_append` | | `true` → zobrazí tlačítko „Přidat řádek" |
| `allow_delete` | | `true` → zobrazí tlačítko smazání na každém řádku |

---

### Skupina sekcí (`section_group`)

Seskupí více subsekcí do Bootstrap accordionu. Každá subsekce je skládatelný panel. První subsekce je výchozně otevřena. Nastavením `always_expanded: true` na subsekcí ji zafixujete v otevřeném stavu.

```json
{
  "id": "dalsi_detaily",
  "type": "section_group",
  "title": "Dalsi detaily",
  "subsections": [
    {
      "id": "kontext",
      "type": "form",
      "title": "Kontext incidentu",
      "note": "vyplnte pokud je relevantni",
      "fields": [
        { "key": "oddeleni",  "label": "Oddeleni",      "type": "text",     "editable": true, "value": null },
        { "key": "dopad",     "label": "Rozsah dopadu", "type": "textarea", "editable": true, "value": null }
      ]
    },
    {
      "id": "dotcene_polozky",
      "type": "table",
      "title": "Dotcene polozky",
      "always_expanded": true,
      "columns": [
        { "key": "typ",         "label": "Typ",         "type": "select", "editable": true, "options": ["Server", "Stanice", "Ucet", "Aplikace"] },
        { "key": "identifikator","label": "Identifikator","type": "text",  "editable": true },
        { "key": "poznamka",    "label": "Poznamka",    "type": "text",   "editable": true }
      ],
      "allow_append": true,
      "allow_delete": true,
      "rows": []
    }
  ]
}
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní identifikátor sekce |
| `type` | ✓ | `"section_group"` |
| `title` | ✓ | Nadpis karty |
| `subsections[]` | ✓ | Seznam subsekcí (panely accordionu) |
| `subsections[].id` | ✓ | Identifikátor subsekce |
| `subsections[].type` | ✓ | Typ subsekce — libovolný registrovaný typ (typicky `form` nebo `table`) |
| `subsections[].title` | ✓ | Nadpis panelu accordionu |
| `description` | | Podnadpis v záhlaví karty |
| `subsections[].note` | | Šedý text vpravo od nadpisu panelu |
| `subsections[].always_expanded` | | `true` → panel nelze sbalit |

---

## Typy polí

| `type` | Widget | Poznámka |
|--------|--------|---------|
| `text` | `<input type="text">` | Jednořádkový textový vstup |
| `textarea` | `<textarea>` | Víceřádkový textový vstup |
| `select` | `<select>` | Výběr ze seznamu; povinný klíč `options[]` |
| `datetime` | `<input type="datetime-local">` | Výběr data a času |
| *(neznámý)* | `<input type="text">` | Záložní chování — vykreslí se jako `text` |

Každé pole v sekci `form` nebo `header` vyžaduje `key`, `label`, `type`, `editable` a `value`. Volitelné klíče:

| Klíč | Popis |
|------|-------|
| `example` | Placeholder text zobrazený v inputu (hodnota z klonování šablony) |
| `placeholder` | UI hint zobrazený v inputu; nikdy se neuloží jako hodnota |
| `hint` | Nápověda zobrazená pod labelem |
| `options[]` | Povinné pro `type: "select"` — list hodnot výběru |
| `option_hints{}` | Per-option hint pod select boxem: `{ "vysoka": "Vyrazny dopad" }` |
| `auto_value` | Backend vyplní automaticky při vytvoření záznamu |
| `is_example` | `true` → hodnota šablony se zobrazí jako placeholder; vyčistí se při klonování |
| `visible_if` | Výraz — skryje pole pokud není splněn (viz podmíněná viditelnost) |
| `required_if` | Výraz — zobrazí `*` u labelu pokud je splněn |

Pokud `editable: false`, pole se vykreslí jako šedý read-only text. Hodnota `null` znamená prázdné.

---

## Extension API

### `UniForms.registerRenderer(type, fn)`

Zaregistruje vlastní typ sekce bez modifikace `uniforms.js`.

Funkce renderer přijme objekt sekce a vrátí DOM element (nebo `null`).

**Krok 1 — napište render funkci:**

```javascript
function renderTimelineSection(section) {
    const wrap = document.createElement('div');
    wrap.className = 'p-3';
    (section.events || []).forEach(event => {
        const row = document.createElement('div');
        row.className = 'd-flex gap-3 mb-2 align-items-start';

        const time = document.createElement('div');
        time.className = 'text-muted small text-nowrap';
        time.textContent = event.time || '';

        const desc = document.createElement('div');
        desc.textContent = event.description || '';

        row.appendChild(time);
        row.appendChild(desc);
        wrap.appendChild(row);
    });
    return wrap;
}
```

**Krok 2 — zaregistrujte renderer:**

```javascript
// Zavolejte po načtení uniforms.js, před voláním UniForms.render()
UniForms.registerRenderer('timeline', renderTimelineSection);
```

**Krok 3 — použijte v šabloně:**

```json
{
  "id": "casova_osa",
  "type": "timeline",
  "title": "Casova osa udalosti",
  "events": [
    { "time": "09:14", "description": "Pozadavek prijat" },
    { "time": "09:47", "description": "Prirazen na support tym" },
    { "time": "11:30", "description": "Problem vyresen" }
  ]
}
```

Extension JS soubory (registrující custom renderery) se načtou po `uniforms.js` — viz sekce Extension JS v `WEB_RENDERING.md`.

---

## `UniForms._helpers`

Interní pomocné funkce jsou dostupné přes `UniForms._helpers` pro použití v extension rendererech:

```javascript
const {
    el,               // createElement se třídou: el('div', 'text-muted')
    setHTML,          // element.innerHTML = sanitizeHTML(html)
    sanitizeHTML,     // XSS sanitizace HTML řetězce
    renderForm,       // vykreslí pole formuláře do containeru
    buildTableHead,   // vytvoří <thead> pro tabulku
    makeDeleteBtn,    // tlačítko smazání řádku
    renderFieldRow,   // vytvoří .field-row div pro jedno pole
    renderInfoGrid,   // vykreslí read-only info-grid (pro header sekce)
    buildOptions,     // naplní <select> ze seznamu options
    renderFieldInput  // vytvoří input/select/textarea pro pole
} = UniForms._helpers;
```

> **Poznámka:** Toto jsou interní API, která se mohou měnit mezi verzemi. Pokud možno stavějte svůj renderer na standardních DOM API.

---

## Podmíněná viditelnost a povinnost

Výrazy `visible_if` a `required_if` se vyhodnocují klientsky funkcí `evalExpr(expr, fields)`.

**Podporovaná syntaxe:**

| Výraz | Podmínka |
|-------|---------|
| `pole == 'hodnota'` | pole má přesně tuto hodnotu |
| `pole != 'hodnota'` | pole nemá tuto hodnotu |
| `pole == null` | pole je prázdné nebo `null` |
| `pole != null` | pole má libovolnou hodnotu |
| `vyraz1 && vyraz2` | obě podmínky musí platit (AND) |
| `vyraz1 \|\| vyraz2` | alespoň jedna podmínka musí platit (OR) |

**Příklad:**

```json
{
  "key": "duvod_eskalace",
  "label": "Duvod eskalace",
  "type": "textarea",
  "editable": true,
  "value": null,
  "visible_if": "priorita == 'kriticka' || priorita == 'vysoka'",
  "required_if": "priorita == 'kriticka'"
}
```

`applyConditionals(fields, container)` zaregistruje `change` event na kontejner a aktualizuje viditelnost a `*` u labelů při každé změně pole.

---

## Bezpečnostní model

Veškerý HTML obsah pocházející z JSON (labely, nadpisy, hinty, texty kroků) prochází `sanitizeHTML()` před vložením do DOM. Tato funkce:

- Parsuje HTML v izolovaném dokumentu `DOMParser` — skripty a styly se v tomto kontextu nespustí.
- Odstraní elementy: `<script>`, `<iframe>`, `<object>`, `<embed>`, `<link>`, `<meta>`.
- Odstraní všechny atributy začínající `on` (např. `onclick`, `onmouseover`) a `href="javascript:"`.

Hodnoty zadávané analytiky (obsah inputů a textarey) **nikdy nevstoupí do `innerHTML`** — čtou a zapisují se přes DOM `.value`, které HTML neparsuje. Sanitizace vstupu na frontendu není nutná.

---

## Přehled veřejného API

`uniforms.js` je zabalen v IIFE a vystavuje jeden globální objekt `UniForms`. Žádné interní funkce nejsou viditelné zvenčí.

| Funkce | Popis |
|--------|-------|
| `UniForms.render(sections, container)` | Hlavní entry point — vykreslí pole sekcí do DOM kontejneru |
| `UniForms.registerRenderer(type, fn)` | Zaregistruje vlastní renderer pro nový typ sekce |
| `UniForms.setReadOnly(container, isReadOnly)` | Přepne celý formulář do read-only nebo editovatelného režimu |
| `UniForms._helpers` | Objekt vystavující interní pomocné funkce pro extension renderery |

### Interní renderery (volané přes registry)

Nejsou součástí veřejného API, ale lze je přepsat přes `UniForms.registerRenderer`:

| Interní funkce | Typy sekcí |
|----------------|-----------|
| `renderHeader(section)` | `header`, `workbook_header`, `playbook_header`, `record_header` |
| `renderFormSection(section)` | `form` |
| `renderChecklist(section)` | `checklist` |
| `renderTable(section)` | `table` |
| `renderSectionGroup(section)` | `section_group` |
| `renderContactTable(section)` | `contact_table` |
| `renderItemTable(section)` | `item_table`, `assets_table` |
| `renderTaskTable(section)` | `task_table`, `action_table` |
