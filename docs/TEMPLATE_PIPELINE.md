# Template Pipeline: YAML → Záznam

Tento dokument popisuje celý pipeline, který transformuje YAML soubor šablony na JSON dokument záznamu připravený k vyplnění.

Určeno pro: vývojáře rozšiřující backend a autory šablon, kteří potřebují pochopit, co systém s jejich YAML dělá.

---

## Jak to funguje?

YAML šablony jsou autorsky přívětivý formát pro popis struktury záznamu — zkrácená syntaxe, komentáře, příkladové hodnoty. Aplikace nepředává surový YAML frontendu. Každý YAML soubor projde třífázovým pipeline:

1. **Parsování** — `yaml.safe_load()` převede YAML na Python dict.
2. **Normalizace** — doplní výchozí hodnoty, vygeneruje chybějící ID, rozbalí zkrácenou syntaxi kroků. Výsledkem je kompletní, konzistentní datová struktura.
3. **Klonování** — při vytvoření záznamu se šablona hluboce zkopíruje, příkladové hodnoty se přesunou na placeholdery a pole `auto_value` se naplní runtime hodnotami (ID záznamu, metadata šablony). Výsledek se serializuje jako JSON a uloží do `data/records/`.

```
data/schemas/{collection_id}/helpdesk-pozadavek-v1.yaml
    │   yaml.safe_load()
    ▼
Python dict — surová data šablony
    │   _resolve_extends()  [pouze pokud šablona dědí]
    ▼
Python dict — sekce rozšířeny o sekce rodiče
    │   _normalize_template()
    ▼
Normalizovaná struktura — kompletní ID, výchozí hodnoty, kroky jako dicts
    │   UniTemplate Pydantic model
    ▼
GET /api/v1/templates/{collection_id}/{template_id}  →  JSON odpověď
    │
    │   POST /api/v1/records/{collection_id}/ { "template_id": "helpdesk-pozadavek-v1" }
    ▼
copy.deepcopy(sections)
    │   _strip_examples()
    │   _fill_auto_values()
    ▼
UniRecord.data  →  JSON soubor data/records/{collection_id}/REC-202603-0042.json
```

Šablona samotná se nikdy nemění. Každý záznam dostane vlastní hlubokou kopii sekcí, izolovanou od ostatních záznamů i od šablony.

---

## Krok za krokem

### Co se stane na `POST /api/v1/records/`

```bash
curl -X POST http://localhost:8080/api/v1/records/ \
     -H "Content-Type: application/json" \
     -H "Cookie: uniforms_token=<token>" \
     -d '{"template_id": "helpdesk-pozadavek-v1"}'
```

Systém provede tyto kroky v tomto pořadí:

1. Načte `data/schemas/helpdesk/helpdesk-pozadavek-v1.yaml`, spustí dědičnost (`_resolve_extends`) a normalizaci (`_normalize_template`).
2. Vygeneruje `record_id` ve formátu konfigurovaném v `uniforms.yaml` (např. `REC-202603-0042`).
3. Sestaví mapu `auto_values` — `record_id`, `template_name`, `template_version`, `last_saved`, všechna pole `meta.*`.
4. Hluboce zkopíruje `sections` ze šablony (`copy.deepcopy`).
5. Zavolá `_strip_examples()` — příkladové hodnoty přesune do klíče `example`, nastaví `value`/`analyst_note` na `null`.
6. Zavolá `_fill_auto_values()` — naplní pole s `auto_value` z mapy.
7. Uloží `REC-202603-0042.json` do `data/records/`.
8. Vrátí `UniRecord` jako JSON s HTTP 201.

---

## Fáze 1 — Parsování

`TemplateService.list_templates()` a `get_template()` čtou soubory z adresáře `data/schemas/{collection_id}/` (konfigurováno v SQLite jako `schemas_dir`).

```python
data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
```

Závislost je pouze na souborovém systému. Poškozený YAML soubor zapíše `WARNING` do logu a přeskočí se — ostatní šablony se načtou normálně.

`TemplateService` je vždy volán s kontextem kolekce — načítá pouze soubory z příslušného podadresáře `data/schemas/{collection_id}/`.

### Dědičnost šablon (`_resolve_extends`)

Pokud šablona deklaruje `extends: <parent_template_id>`, systém nalezne rodičovskou šablonu v libovolném adresáři a předřadí její sekce před sekce potomka.

```yaml
# data/templates/helpdesk_pozadavek_v1.yaml
extends: base-header-v1
template_id: helpdesk-pozadavek-v1
name: Helpdesk Pozadavek
sections:
  - id: popis
    type: form
    title: Popis pozadavku
    fields:
      - key: popis_problemu
        label: Popis problemu
        type: textarea
```

Výsledek po rozbalení dědičnosti: sekce z `base-header-v1` + sekce `popis`. Šablony s `abstract: true` se nezobrazují v přehledu, ale jsou dostupné jako rodiče.

---

## Fáze 2 — Normalizace (`_normalize_template`)

Normalizace umožňuje psát šablony v úsporném formátu bez opakujícího se boilerplate. Spouští se ihned po parsování, před Pydantic validací.

**Pravidlo: existující hodnoty se nikdy nepřepisují** — normalizace používá výhradně `setdefault()`. Šablony v plném formátu jsou plně zpětně kompatibilní.

Normalizace běží rekurzivně přes všechny sekce včetně `subsections`.

### Výchozí hodnoty polí (`_norm_field`)

Každé formulářové pole (`fields[]`) dostane chybějící klíče.

Před normalizací (zkrácený zápis):
```yaml
- key: nazev_pozadavku
  label: Nazev pozadavku
```

Po normalizaci:
```yaml
- key: nazev_pozadavku
  label: Nazev pozadavku
  type: text
  editable: true
  value: null
```

### Zkratka `auto:` (`_norm_field`)

Klíč `auto: <zdroj>` je zkratka pro `editable: false` + `auto_value: <zdroj>`.

Před normalizací:
```yaml
- key: id_zaznamu
  label: ID zaznamu
  auto: record_id
```

Po normalizaci:
```yaml
- key: id_zaznamu
  label: ID zaznamu
  type: text
  editable: false
  auto_value: record_id
  value: null
```

### Příkladové hodnoty (`_norm_field`, `_norm_step`)

Klíč `example:` označí pole jako příkladové — hodnota se zobrazí jako placeholder a při klonování se přesune.

Před normalizací (formulářové pole):
```yaml
- key: pricina
  label: Pricina
  type: textarea
  example: Vyprsela platnost hesla uzivatele
```

Po normalizaci:
```yaml
- key: pricina
  label: Pricina
  type: textarea
  is_example: true
  value: Vyprsela platnost hesla uzivatele
```

> **Poznámka:** Klíč `value` se při normalizaci nastaví na obsah `example`. Teprve klonování (`_strip_examples`) přesune tuto hodnotu na klíč `example` a nastaví `value: null`.

### Rozbalení string kroku (`_norm_step`)

Krok zapsaný jako prostý řetězec se rozbalí na plný dict.

Před normalizací:
```yaml
steps:
  - Potvrdte, ze problem je reprodukovatelny.
```

Po normalizaci:
```json
{
  "id": "triage_group_01",
  "action": "Potvrdte, ze problem je reprodukovatelny.",
  "analyst_note": null,
  "done": false
}
```

### Flat `steps:` → `step_groups` (`_norm_section`)

V2 šablony mohou psát kroky přímo pod sekcí bez pojmenované skupiny.

Před normalizací:
```yaml
- id: triage
  type: checklist
  title: Triage
  steps:
    - Potvrdte, ze problem je reprodukovatelny.
    - Identifikujte postizene uzivatele.
```

Po normalizaci:
```json
{
  "id": "triage",
  "type": "checklist",
  "title": "Triage",
  "step_groups": [
    {
      "id": "triage_group_1",
      "title": null,
      "steps": [
        { "id": "triage_triage_group_1_01", "action": "Potvrdte, ze problem je reprodukovatelny.", "done": false, "analyst_note": null },
        { "id": "triage_triage_group_1_02", "action": "Identifikujte postizene uzivatele.", "done": false, "analyst_note": null }
      ]
    }
  ]
}
```

### Generování ID (`_slugify`)

Sekce, skupiny kroků a kroky bez explicitního `id` dostanou auto-generované ID z jejich `title` přes `_slugify()`.

```
"Pocatecni diagnostika"  →  "pocatecni_diagnostika"
```

`_slugify` provede Unicode NFD normalizaci, odstraní diakritiku, převede na lowercase a nahradí mezery a pomlčky podtržítky.

Formát ID kroku: `{section_id}_{group_id}_{pozice:02d}`, například: `triage_pocatecni_diagnostika_01`.

> **Pozor:** Ruční `id` v YAML šabloně má vždy přednost. Používejte explicitní ID všude, kde potřebujete stabilní referenci (např. pro logy nebo budoucí migraci dat).

---

## Fáze 3 — Klonování záznamu (`record_service`)

Klonování spouští `POST /api/v1/records/`. Šablona musí být nejprve normalizována — vždy přes `TemplateService.get_template()`, nikdy přímým čtením souboru.

### Hluboká kopie

```python
sections = copy.deepcopy(template.sections)
```

Hluboká kopie zajistí, že editace záznamu neovlivní šablonu ani jiné záznamy.

### Zpracování příkladových hodnot (`_strip_examples`)

Pole s `is_example: true` mají v normalizované šabloně hodnotu uloženou v `value` nebo `analyst_note`. Při klonování `_strip_examples` přesune tuto hodnotu do klíče `example` a nastaví `value`/`analyst_note` na `null`.

**Formulářové pole — před klonováním (v normalizované šabloně):**
```json
{
  "key": "pricina",
  "label": "Pricina",
  "type": "textarea",
  "is_example": true,
  "value": "Vyprsela platnost hesla uzivatele"
}
```

**Po klonování (v novém záznamu):**
```json
{
  "key": "pricina",
  "label": "Pricina",
  "type": "textarea",
  "is_example": true,
  "value": null,
  "example": "Vyprsela platnost hesla uzivatele"
}
```

**Krok checklistu — před klonováním (v normalizované šabloně):**
```json
{
  "id": "triage_01",
  "action": "Zdokumentujte chybovou hlasku.",
  "is_example": true,
  "analyst_note": "Chyba 0x80070005: Pristup odepren",
  "done": false
}
```

**Po klonování (v novém záznamu):**
```json
{
  "id": "triage_01",
  "action": "Zdokumentujte chybovou hlasku.",
  "is_example": true,
  "analyst_note": null,
  "example": "Chyba 0x80070005: Pristup odepren",
  "done": false
}
```

Frontend zobrazí hodnotu z klíče `example` jako šedý placeholder v textarea poznámky.

### Naplnění auto-hodnot (`_fill_auto_values`)

Pole s `auto_value` dostanou hodnotu nastavenou při vytvoření záznamu. Nahrazení běží rekurzivně přes celou strukturu sekcí.

| `auto_value` | Vyplní se |
|---|---|
| `record_id` | Vygenerované ID záznamu, např. `REC-202603-0042` |
| `template_name` | `template.name` — zobrazovaný název šablony |
| `template_version` | `template.version` — verze šablony |
| `template_status` | `template.status` — stav šablony (`active`, `draft`, `deprecated`) |
| `last_saved` | Časová značka vytvoření záznamu; aktualizuje se při každém dalším uložení |
| `meta.<klic>` | Libovolný klíč z bloku `meta:` šablony (např. `meta.mitre_tactic` pro SOC extension) |

Pole s `auto_value` mají typicky `editable: false` — analytik je nemůže změnit.

---

## Přehled API endpointů

| Metoda | Endpoint | Přístup | Popis |
|--------|----------|---------|-------|
| `GET` | `/api/v1/templates/{collection_id}/` | auth | Seznam šablon kolekce (normalizované, jako JSON) |
| `GET` | `/api/v1/templates/{collection_id}/{template_id}` | auth | Detail šablony |
| `GET` | `/api/v1/templates/{collection_id}/{template_id}/source` | collection admin | Zdrojový YAML (pro editor) |
| `PUT` | `/api/v1/templates/{collection_id}/{template_id}` | collection admin | Uložení upraveného YAML |
| `POST` | `/api/v1/templates/{collection_id}/` | collection admin | Vytvoření nového souboru šablony |
| `DELETE` | `/api/v1/templates/{collection_id}/{template_id}` | collection admin | Smazání souboru šablony |
| `GET` | `/api/v1/records/{collection_id}/` | auth | Seznam záznamů kolekce |
| `POST` | `/api/v1/records/{collection_id}/` | auth | Vytvoření záznamu ze šablony |
| `GET` | `/api/v1/records/{collection_id}/{record_id}` | auth | Detail záznamu |
| `PATCH` | `/api/v1/records/{collection_id}/{record_id}` | auth | Uložení záznamu (status + data) |
| `DELETE` | `/api/v1/records/{collection_id}/{record_id}` | collection admin | Smazání záznamu |

---

## Reference — funkce a třídy

| Identifikátor | Soubor | Popis |
|---|---|---|
| `_slugify(text)` | `app/services/template_service.py` | Převede title na ASCII slug s podtržítky |
| `_norm_column(col)` | `app/services/template_service.py` | Doplní výchozí `type` a `editable` pro sloupec v2 tabulky |
| `_norm_field(field)` | `app/services/template_service.py` | Doplní `type`, `editable`, `value`; zpracuje `auto:` zkratku a `example:` |
| `_norm_step(step, idx, prefix)` | `app/services/template_service.py` | Rozbalí string krok, doplní `id`, `done`, `analyst_note` |
| `_norm_group(group, idx, section_id)` | `app/services/template_service.py` | Doplní group ID, normalizuje kroky |
| `_norm_section(section, idx)` | `app/services/template_service.py` | Doplní section ID, rekurzivně normalizuje pole, kroky a subsekce |
| `_normalize_template(data)` | `app/services/template_service.py` | Entry point — iteruje přes všechny sekce |
| `_resolve_extends(data, all_dirs)` | `app/services/template_service.py` | Rozbalí dědičnost šablony; předřadí sekce rodiče |
| `TemplateService` | `app/services/template_service.py` | CRUD pro YAML soubory šablon; podporuje více adresářů |
| `get_template_service(db)` | `app/services/template_service.py` | FastAPI dependency — vrátí `TemplateService` s cestou z DB + extension adresáři |
| `generate_record_id()` | `app/services/record_service.py` | Generuje ID záznamu ve formátu konfigurovaném v `uniforms.yaml` |
| `_build_auto_values(record_id, template)` | `app/services/record_service.py` | Sestaví mapu `auto_value → hodnota` pro daný záznam |
| `_strip_examples(obj)` | `app/services/record_service.py` | Přesune `is_example` hodnoty na klíč `example`, nastaví `value`/`analyst_note` na `null` |
| `_fill_auto_values(obj, auto_values)` | `app/services/record_service.py` | Naplní pole s `auto_value` z mapy runtime hodnot |
| `_update_last_saved(obj, timestamp)` | `app/services/record_service.py` | Aktualizuje `last_saved` pole při každém uložení záznamu |
| `_clone_template_sections(sections)` | `app/services/record_service.py` | Interní: `deepcopy` + `_strip_examples` (volá `create_record`) |
| `create_record(storage, template, username)` | `app/services/record_service.py` | Celý pipeline: klonování → auto_values → uložení |
| `UniRecord` | `app/models/record.py` | Pydantic model záznamu |
| `UniTemplate` | `app/models/template.py` | Pydantic model normalizované šablony |
