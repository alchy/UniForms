# Šablony a záznamy v UniForms

Tento dokument popisuje, co jsou šablony a záznamy, jak funguje pipeline od YAML souboru po vyplněný formulář, jaké typy sekcí a polí lze použít, a jak se využívají pokročilé funkce jako podmíněná viditelnost, automatické hodnoty nebo dědičnost šablon.

---

## 1. Co je šablona a co je záznam

**Šablona** je YAML soubor uložený v `data/schemas/{collection_id}/`. Definuje strukturu dokumentu: jaké sekce obsahuje, jaká pole se v každé sekci zobrazují, jaké kroky má analytik splnit a jaké hodnoty se vyplní automaticky. Šablona se při práci s záznamy nikdy nezapisuje — slouží výhradně jako vzor. Jeden soubor šablony může být použit pro vytvoření libovolného počtu záznamů.

**Záznam** je JSON soubor uložený v databázi (`data/uniforms.db`) a souborovém systému (`data/records/{collection_id}/`). Vzniká klonováním šablony: systém zkopíruje celou strukturu sekci a polí do nového dokumentu, doplní automatické hodnoty (ID záznamu, přihlášený uživatel, čas vytvoření) a uloží ho. Od tohoto okamžiku je záznam nezávislý na šabloně — pozdější změny šablony existující záznamy neovlivní.

Příslušnost šablony ke kolekci je dána umístěním souboru: soubor v `data/schemas/helpdesk/` automaticky patří do kolekce `helpdesk`. Žádný klíč `collection:` v YAML šablony neexistuje.

---

## 2. Pipeline: od YAML k záznamu

```
YAML soubor šablony
    │
    ▼
TemplateService.get_template()
    │
    ├─ 1. Parsování YAML → dict (PyYAML safe_load)
    │
    ├─ 2. Dědičnost (extends:)
    │      Načte rodičovskou šablonu, rekurzivně ji vyřeší,
    │      a předřadí její sekce před sekce potomka.
    │
    └─ 3. Normalizace
           • auto: <zdroj>  →  editable: false + auto_value: <zdroj>
           • example: hodnota  →  field.value (označí is_example: true)
           • Chybějící type  →  "text"
           • Chybějící editable  →  true
           • Chybějící value  →  null
           • Flat steps:  →  step_groups: [{title: null, steps: [...]}]
           • Chybějící id sekce/kroku/skupiny  →  slugify z title
    │
    ▼
UniTemplate (normalizovaný objekt)
    │
    ▼
POST /api/v1/records/{collection_id}/
record_service.create_record()
    │
    ├─ Vygeneruje record_id dle id_format kolekce
    │
    ├─ Hluboce zkopíruje sekce ze šablony
    │
    ├─ _strip_examples(): přesune example hodnoty do pole "example",
    │   hodnotu pole/kroku resetuje na null
    │
    ├─ _fill_auto_values(): vyplní pole označená auto_value
    │   hodnotami z mapy (record_id, current_user, now, meta.*, ...)
    │
    └─ Vloží workflow_states a initial_state z konfigurace kolekce
    │
    ▼
UniRecord uložený do databáze
```

Každá fáze pipeline je bezstavová — šablona na disku se nemění, záznam je kompletně samostatný dokument.

---

## 3. Rychlý start

Níže je kompletní minimální šablona. Obsahuje záhlaví a jeden formulář. Uložte ji jako nový soubor, otevřete aplikaci a vytvořte první záznam.

**Krok 1 — Uložte soubor**

Vytvořte soubor `data/schemas/helpdesk/zakladni-v1.yaml` s tímto obsahem:

```yaml
template_id: helpdesk-zakladni-v1
name: "Helpdesk – základní požadavek"
version: '1.0'
status: draft
description: "Šablona pro IT helpdesk požadavky prvního stupně."

sections:
  - id: header
    title: Hlavička
    type: header
    fields:
      - key: record_id
        label: ID záznamu
        auto: record_id
      - key: template_name
        label: Šablona
        auto: template_name
      - key: title
        label: Název požadavku
        placeholder: 'např.: Tiskárna offline – budova B'
      - key: coordinator
        label: Řešitel

  - id: details
    title: Podrobnosti
    type: form
    fields:
      - key: priority
        label: Priorita
        type: select
        options: ["Nízká", "Střední", "Vysoká", "Kritická"]
      - key: description
        label: Popis problému
        type: textarea
        placeholder: "Popište problém stručně a srozumitelně."

  - id: postup
    title: Postup řešení
    type: checklist
    steps:
      - "Potvrďte přijetí požadavku a kontaktujte zadatele."
      - "Prozkoumejte příčinu."
      - "Aplikujte opravu nebo řešení."
      - "Ověřte řešení se zadatelem a uzavřete záznam."
```

**Krok 2 — Otevřete šablonu v UI**

V aplikaci přejděte na sekci **Šablony** ve vybrané kolekci. Šablona `helpdesk-zakladni-v1` se zobrazí se stavem `draft`.

**Krok 3 — Vytvořte záznam**

Klikněte na tlačítko **Nový záznam** u dané šablony. Systém vytvoří nový záznam, vyplní automatická pole (ID záznamu, název šablony) a otevře ho k editaci. Po ověření funkčnosti změňte `status` v YAML souboru z `draft` na `active`.

---

## 4. Struktura YAML šablony — horní úroveň

```yaml
template_id: helpdesk-zakladni-v1
name: "Helpdesk – základní požadavek"
version: '1.0'
status: active
description: "Standardní šablona pro IT helpdesk požadavky prvního stupně."
abstract: false
extends: null

meta:
  sla_hodiny: 8
  kategorie: "IT Support"

workflow:
  initial_state: new
  states:
    - id: new
      label: "Nové"
      color: secondary
    - id: in_progress
      label: "Zpracovává se"
      color: warning
    - id: closed
      label: "Uzavřeno"
      color: success

sections:
  - id: header
    type: header
    title: "Hlavička"
    fields: []
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `template_id` | ✓ | Unikátní identifikátor šablony v rámci kolekce; doporučený formát `nazev-v1` (malá písmena, pomlčky) |
| `name` | ✓ | Zobrazovaný název v UI |
| `version` | ✓ | Verze šablony — vždy jako řetězec uzavřený do uvozovek, např. `'1.0'` |
| `status` | ✓ | `active` \| `draft` \| `deprecated`; nové šablony začínají jako `draft` |
| `sections[]` | ✓ | Seznam sekcí šablony |
| `description` | | 1–2 věty popisující účel šablony; zobrazí se v přehledu šablon |
| `abstract` | | `true` = šablona slouží pouze jako základ pro dědičnost, nezobrazí se v dashboardu (výchozí: `false`) |
| `extends` | | `template_id` rodičovské šablony; sekce rodiče jsou vloženy před sekce potomka |
| `meta{}` | | Libovolné doménové klíče; hodnoty jsou přístupné v polích přes `auto: meta.<klíč>` |
| `workflow{}` | | Přepíše workflow kolekce jen pro tuto šablonu; obsahuje `initial_state` a `states[]` |

> **Poznámka:** Hodnotu `version` vždy uzavřete do jednoduchých uvozovek: `version: '1.0'`. Bez uvozovek YAML parsuje `1.0` jako číslo a dojde k chybě při načítání šablony.

---

## 5. Typy sekcí

### `header` — záhlaví záznamu

Povinná první sekce každé šablony. Zobrazí se jako info-grid: automaticky vyplněná pole (ID záznamu, šablona, koordinátor) jsou vedle sebe v kompaktním přehledu. Typicky obsahuje kombinaci automaticky vyplněných polí (`auto:`) a editovatelných polí (název záznamu, řešitel).

```yaml
- id: header
  title: Záhlaví záznamu
  type: header
  fields:
    - key: record_id
      label: ID záznamu
      auto: record_id
    - key: template_name
      label: Šablona
      auto: template_name
    - key: case_title
      label: Název incidentu
      type: text
      editable: true
      placeholder: Krátký výstižný popis pro odlišení od ostatních záznamů
      value: null
    - key: coordinator
      label: Koordinátor
      type: text
      editable: true
      value: null
    - key: created_at
      label: Datum vytvoření
      type: datetime
      auto: now
    - key: last_saved
      label: Poslední aktualizace
      type: datetime
      auto: last_saved
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní ID sekce (auto-generované ze `title` pokud chybí) |
| `type` | ✓ | `"header"` |
| `title` | ✓ | Nadpis karty |
| `fields[]` | ✓ | Pole sekce — viz kapitola Typy polí |
| `hint` | | Modrý informační box zobrazený nad sekcí |

---

### `form` — formulářová sekce

Dvousloupcová mřížka s libovolnými poli. Label je vlevo, vstupní pole vpravo. Volitelný klíč `hint` zobrazí modrý informační box nad formulářem. Pole mohou mít podmíněnou viditelnost (`visible_if`) nebo podmíněnou povinnost (`required_if`).

```yaml
- id: classification
  title: Klasifikace incidentu
  type: form
  hint: "Vyplní analytik na základě počáteční analýzy."
  fields:
    - key: source_type
      label: Zdroj detekce
      type: select
      editable: true
      options: ["SIEM", "EDR", "Hlášení uživatele", "Threat Intel"]
      value: null
    - key: severity
      label: Závažnost
      type: select
      editable: true
      options: ["Kritická", "Vysoká", "Střední", "Nízká"]
      value: null
    - key: affected_systems
      label: Zasažené systémy
      type: textarea
      editable: true
      placeholder: "Např. DC01, WS-FINANCE-01"
      value: null
    - key: detection_time
      label: Čas detekce
      type: datetime
      editable: true
      value: null
    - key: external_source_name
      label: Název externího zdroje
      type: text
      editable: true
      value: null
      visible_if: "source_type == 'Threat Intel'"
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní ID sekce |
| `type` | ✓ | `"form"` |
| `title` | ✓ | Nadpis karty |
| `fields[]` | ✓ | Formulářová pole |
| `hint` | | Modrý informační box nad formulářem |

---

### `checklist` — kontrolní seznam

Sekce s kroky postupu — každý krok je checkbox, který analytik odškrtne po splnění. Kroky lze zapsat jako plochý seznam (`steps:`) nebo sdružovat do pojmenovaných skupin (`step_groups:`). Plochý seznam je automaticky zabalený do jedné skupiny bez nadpisu.

Ke každému kroku lze přidat `hint` (nápověda pod krokem) nebo `example` (vzorový text v poli pro poznámku analytika).

**Varianta 1 — plochý seznam kroků:**

```yaml
- id: triage
  title: Triage postup
  type: checklist
  steps:
    - "Ověř autenticitu hlášení"
    - "Zkontroluj logy SIEM za posledních 24h"
    - action: "Eskaluj pokud nelze vyřešit do 1 hodiny"
      hint: "Postup eskalace viz interní wiki – sekce SLA matice."
    - action: "Zdokumentuj zasažené systémy"
      example: "DC01, WS-NOVAK-01 (podezřelé přihlášení z IP 185.x.x.x)"
```

**Varianta 2 — strukturované skupiny kroků:**

```yaml
- id: postup
  title: Postup řešení
  type: checklist
  step_groups:
    - title: "Fáze 1 – Ověření"
      note: "cíl: do 15 minut od hlášení"
      hints:
        - "Nejprve zkontrolujte logy – ušetří čas při hovoru s uživatelem."
      steps:
        - id: verify_report
          action: "Ověř autenticitu hlášení"
          done: false
        - id: check_siem
          action: "Zkontroluj logy SIEM za posledních 24h"
          done: false
    - title: "Fáze 2 – Izolace"
      steps:
        - id: isolate_system
          action: "Izoluj zasažený systém od sítě"
          done: false
        - id: preserve_evidence
          action: "Zajisti forenzní obraz disku před jakýmkoli zásahem"
          done: false
```

| Klíč sekce | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní ID sekce |
| `type` | ✓ | `"checklist"` |
| `title` | ✓ | Nadpis karty |
| `steps[]` | ◐ | Plochý seznam kroků (řetězce nebo objekty); nesmí být spolu s `step_groups:` |
| `step_groups[]` | ◐ | Strukturované skupiny kroků; nesmí být spolu s `steps:` |

> **Poznámka:** `steps:` a `step_groups:` jsou vzájemně zaměnitelné — použijte jeden nebo druhý. Flat `steps:` jsou normalizátorem automaticky zabaleny do jedné `step_groups` položky s `title: null`.

| Klíče `step_group` | ✓ | Popis |
|------|:-:|-------|
| `title` | | Název skupiny (`null` = bez viditelného nadpisu) |
| `note` | | Šedý text pod nadpisem skupiny (např. cíl časový rámec) |
| `hints[]` | | Seznam šedých textů zobrazených pod nadpisem skupiny |
| `steps[]` | ✓ | Kroky skupiny |

| Klíče `step` | ✓ | Popis |
|------|:-:|-------|
| `id` | | Auto-generováno ze `action`/`title` nebo pozice pokud chybí |
| `action` | ✓ | Text kroku — instrukce ve formě „co má analytik udělat" |
| `done` | | Počáteční stav checkboxu (výchozí: `false`) |
| `hint` | | Šedý box s provozní poznámkou zobrazený pod krokem |
| `example` | | Vzorový text zobrazený jako placeholder v poli pro poznámku analytika |

---

### `table` — tabulka

Editovatelná tabulka s volitelnou editovatelností per-sloupec. `allow_append_row: true` přidá tlačítko pro nový řádek, `allow_delete_row: true` umožní řádky mazat.

`rows` a `append_row_template` slouží různým fázím — jsou to **nezávislé klíče, ne alternativy**:

- **`rows`** — data *uložená do záznamu* při jeho vytvoření (backend, `record_service`). Řádky jsou součástí JSON záznamu od první chvíle. Vynechání nebo `rows: []` je totéž — tabulka začíná prázdná. `rows: []` nikdy nepiš, je zbytečné.
- **`append_row_template`** — vzor pro tlačítko „+ Přidat řádek" (runtime, prohlížeč). Určuje výchozí hodnoty nového řádku; klíče, které neuvedeš, dostanou `null`. Nemá vliv na počáteční stav záznamu.

Typické použití — **vyber jeden ze tří vzorů**:

```yaml
# 1. Prázdná tabulka, nové řádky mají výchozí hodnoty (nejčastější)
allow_append_row: true
append_row_template:
  status: "Nekontaktován"

# 2. Tabulka s předvyplněnými řádky ze šablony, nové řádky prázdné
allow_append_row: true
rows:
  - name: "Jan Novák"
    role: "Primární kontakt"
    phone: null
    status: "Nekontaktován"

# 3. Předvyplněné řádky i výchozí hodnoty pro nové (výjimečné)
allow_append_row: true
rows:
  - name: "Jan Novák"
    role: "Primární kontakt"
    phone: null
    status: "Nekontaktován"
append_row_template:
  status: "Nekontaktován"
```

Plný příklad sekce (vzor 1):

```yaml
- id: contacts
  title: Kontakty
  type: table
  hint: "Primární a záložní kontakty pro tento incident."
  allow_append_row: true
  allow_delete_row: true
  columns:
    - key: name
      label: Jméno
      type: text
      editable: true
    - key: role
      label: Role
      type: select
      editable: true
      options: ["Primární kontakt", "Záložní kontakt", "CISO", "Vedení"]
    - key: phone
      label: Telefon
      type: text
      editable: true
    - key: status
      label: Stav kontaktování
      type: select
      editable: true
      options: ["Nekontaktován", "Kontaktován", "Odpověděl"]
  append_row_template:
    status: "Nekontaktován"
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní ID sekce |
| `type` | ✓ | `"table"` |
| `title` | ✓ | Nadpis karty |
| `columns[]` | ✓ | Definice sloupců (viz níže) |
| `rows[]` | | Počáteční řádky vložené do záznamu při jeho vytvoření; vynechání = prázdná tabulka |
| `append_row_template{}` | | Výchozí hodnoty pro řádek přidaný uživatelem; neuvedené klíče = `null` |
| `allow_append_row` | | `true` = tlačítko „+ Přidat řádek" (výchozí: `false`) |
| `allow_delete_row` | | `true` = tlačítko pro smazání řádku (výchozí: `false`) |
| `hint` | | Modrý informační box nad tabulkou |
| `hints[]` | | Seznam šedých textů pod tabulkou |

| Klíče `column` | ✓ | Popis |
|------|:-:|-------|
| `key` | ✓ | Klíč hodnoty v řádku |
| `label` | ✓ | Nadpis sloupce |
| `type` | | `text` \| `select` \| `textarea` (výchozí: `text`) |
| `editable` | | `true` = editovatelný; `false` = read-only (výchozí: `false`) |
| `options[]` | ◐ | Povinné pokud `type: select` |

---

### `section_group` — skupina sekcí

Sdružuje více logicky souvisejících sekcí pod jeden nadpis jako accordionový kontejner. Podsekce jsou libovolné typy (`form`, `table`, `checklist`). Volitelný klíč `always_expanded: true` na podsekci zabrání jejímu sbalení.

```yaml
- id: closure
  title: Uzavření incidentu
  type: section_group
  sections:
    - id: closure_base
      type: form
      title: Závěrečné hodnocení
      always_expanded: true
      fields:
        - key: root_cause
          label: Příčina incidentu
          type: textarea
          editable: true
          value: null
          example: "Heslo uživatele bylo phishingem kompromitováno v kampani z 15. 3."
        - key: closure_date
          label: Datum uzavření
          type: datetime
          auto: now
    - id: lessons_learned
      type: checklist
      title: Lessons Learned
      steps:
        - "Analyzuj příčinu incidentu"
        - "Navrhni preventivní opatření"
        - "Aktualizuj playbook"
    - id: action_items
      type: table
      title: Akční body
      allow_append_row: true
      allow_delete_row: true
      columns:
        - key: action
          label: Akce
          type: text
          editable: true
        - key: owner
          label: Odpovědná osoba
          type: text
          editable: true
        - key: due_date
          label: Termín
          type: text
          editable: true
        - key: status
          label: Stav
          type: select
          editable: true
          options: ["Čeká", "Probíhá", "Hotovo"]
      rows: []   # prázdná tabulka při vytvoření záznamu
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | ✓ | Unikátní ID skupiny |
| `type` | ✓ | `"section_group"` |
| `title` | ✓ | Nadpis skupiny |
| `sections[]` | ✓ | Podsekce libovolného typu (`form`, `table`, `checklist`) |
| `sections[].always_expanded` | | `true` = podsekce nelze sbalit |

> **Poznámka:** Klíč pro podsekce je `sections:` (ne `subsections:`). Obě varianty jsou v kódu normalizátoru podporovány, ale doporučená forma je `sections:`.

---

## 6. Typy polí

Pole jsou definována v klíči `fields:` sekcí typu `header` a `form`, nebo v klíči `columns:` sekce `table`.

### `text` — jednořádkový text

Standardní jednořádkový textový vstup. Výchozí typ pokud `type:` chybí.

```yaml
- key: analyst_name
  label: Jméno analytika
  type: text
  editable: true
  value: null
  placeholder: "Např. Jan Novák"
```

### `textarea` — víceřádkový text

Víceřádkový textový vstup pro delší popisy, poznámky nebo dokumentaci.

```yaml
- key: description
  label: Popis incidentu
  type: textarea
  editable: true
  value: null
  placeholder: "Stručný popis situace, dopadu a prvotní analýzy..."
  example: "Uživatel obdržel e-mail s podvodnou přílohou, kliknul na odkaz a zadal přihlašovací údaje."
```

### `select` — výběr ze seznamu

Rozbalovací seznam předdefinovaných hodnot. Klíč `options:` je povinný.

```yaml
- key: severity
  label: Závažnost
  type: select
  editable: true
  options: ["Kritická", "Vysoká", "Střední", "Nízká"]
  value: null
```

### `datetime` — datum a čas

Vstup pro datum a čas (HTML `datetime-local`). Hodnota se ukládá ve formátu `YYYY-MM-DDTHH:MM`.

```yaml
- key: incident_time
  label: Čas incidentu
  type: datetime
  editable: true
  value: null
```

### `number` — číslo

Číselný vstup. Vhodný pro ceny, počty, roky a jiné numerické hodnoty.

```yaml
- key: rok_vyroby
  label: Rok výroby
  type: number
  editable: true
  value: null
```

### Tabulka klíčů pole (platí pro všechny typy)

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `key` | ✓ | Unikátní klíč v rámci sekce; používá se pro odkazování v `visible_if`/`required_if` |
| `label` | ✓ | Zobrazovaný popis pole |
| `type` | | `text` \| `textarea` \| `select` \| `datetime` \| `number` (výchozí: `text`) |
| `editable` | | `true` = analytik může editovat; `false` = read-only (výchozí: `true`; vždy `false` pokud je `auto:` přítomno) |
| `value` | | Počáteční hodnota (výchozí: `null`) |
| `options[]` | ◐ | Povinné pokud `type: select` |
| `auto` | | Zdroj automatické hodnoty — viz kapitola Klíč `auto:` |
| `example` | | Předvyplněná ukázková hodnota; zobrazí se jako šedý placeholder, při vytvoření záznamu se hodnota resetuje na `null` |
| `placeholder` | | Hint text zobrazený uvnitř prázdného vstupního pole (HTML `placeholder`); nezapisuje se jako hodnota |
| `required` | | `true` = pole je označeno jako povinné (vizuální indikátor) |
| `visible_if` | | Výraz podmíněné viditelnosti — viz kapitola Podmíněná viditelnost |
| `required_if` | | Výraz podmíněné povinnosti — viz kapitola Podmíněná viditelnost |
| `hint` | | Šedý text zobrazený pod vstupním polem |

---

## 7. Klíč `auto:` — automatické hodnoty

Pole s klíčem `auto:` je vždy read-only (`editable: false`). Jeho hodnota se vyplní automaticky při vytvoření záznamu nebo při každém uložení (v případě `last_saved`).

`auto:` je zkratka normalizátoru — při načtení šablony se expanduje na `editable: false` + `auto_value: <zdroj>`.

```yaml
- key: record_id
  label: ID záznamu
  type: text
  auto: record_id

- key: created_by
  label: Vytvořil
  type: text
  auto: current_user

- key: created_at
  label: Vytvořeno
  type: datetime
  auto: now

- key: last_saved
  label: Poslední uložení
  type: datetime
  auto: last_saved

- key: template_name
  label: Název šablony
  type: text
  auto: template_name

- key: template_version
  label: Verze šablony
  type: text
  auto: template_version

- key: mitre_tactic
  label: MITRE Tactic
  type: text
  auto: meta.mitre_tactic
```

| Hodnota `auto` | Popis |
|----------------|-------|
| `record_id` | Vygenerované ID záznamu (např. `REC-202603-0042`) |
| `template_name` | Zobrazovaný název šablony |
| `template_version` | Verze šablony (řetězec, např. `"2.0"`) |
| `current_user` | Username přihlášeného uživatele v okamžiku vytvoření záznamu |
| `now` | Čas vytvoření záznamu ve formátu `YYYY-MM-DDTHH:MM` (lokální timezone) |
| `last_saved` | Čas posledního uložení záznamu; aktualizuje se při každém `PUT /api/v1/records/…` |
| `meta.<klíč>` | Hodnota z bloku `meta:` šablony (např. `meta.mitre_tactic`, `meta.sla_hodiny`) |

> **Poznámka:** Pokud hodnota v `meta:` je seznam, je spojena čárkou do jednoho řetězce (např. `"EDR, SIEM, Firewall"`).

---

## 8. Podmíněná viditelnost (`visible_if`, `required_if`)

Klíče `visible_if` a `required_if` umožňují zobrazit pole nebo označit je jako povinná na základě hodnoty jiného pole ve stejné sekci. Výrazy jsou vyhodnocovány v prohlížeči JavaScriptem při každé změně pole.

```yaml
- id: classification
  title: Klasifikace incidentu
  type: form
  fields:
    - key: source_type
      label: Zdroj detekce
      type: select
      editable: true
      options: ["Interní", "Externí", "Hlášení uživatele"]
      value: null

    - key: external_source_name
      label: Název externího zdroje
      type: text
      editable: true
      value: null
      visible_if: "source_type == 'Externí'"

    - key: user_report_contact
      label: Kontakt na hlásícího
      type: text
      editable: true
      value: null
      visible_if: "source_type == 'Hlášení uživatele'"
      required_if: "source_type == 'Hlášení uživatele'"

    - key: impact
      label: Dopad na provoz
      type: textarea
      editable: true
      value: null
      visible_if: "source_type != null"
      required_if: "source_type == 'Interní' && impact == null"
```

### Syntaxe výrazů

| Výraz | Popis |
|-------|-------|
| `pole == 'hodnota'` | Pole se rovná zadané hodnotě (case-sensitive) |
| `pole != 'hodnota'` | Pole se nerovná zadané hodnotě |
| `pole == null` | Pole je prázdné (hodnota `null` nebo prázdný řetězec) |
| `pole != null` | Pole má neprázdnou hodnotu |
| `výraz1 && výraz2` | Logické AND — obě podmínky musí platit |
| `výraz1 \|\| výraz2` | Logické OR — alespoň jedna podmínka musí platit |

> **Pozor:** `visible_if` a `required_if` pracují pouze s hodnotami polí ve stejné sekci. Odkaz na pole z jiné sekce není podporován.

---

## 9. Klíče `example:` a `placeholder:`

Oba klíče slouží jako nápověda analytikovi, ale fungují odlišně.

```yaml
# example: — předvyplní pole ukázkovou hodnotou (šedý placeholder v záznamu)
# Při vytvoření záznamu se example hodnota zobrazí jako šedý text;
# jakmile analytik začne psát, vzor zmizí. Hodnota pole zůstane null.
- key: root_cause
  label: Kořenová příčina
  type: textarea
  editable: true
  example: "Heslo uživatele bylo kompromitováno phishingovou kampaní z 15. 3."

# placeholder: — zobrazí nápovědu přímo v HTML inputu
# Nezapisuje se nikam jako hodnota. Zmizí při zahájení psaní.
- key: affected_systems
  label: Zasažené systémy
  type: textarea
  editable: true
  placeholder: "Např. DC01, WS-FINANCE-01 (oddělené čárkou)"
  value: null
```

| | `example:` | `placeholder:` |
|--|-----------|----------------|
| Kde se zobrazí | Jako šedý vzorový text v poli záznamu (v JS renderu) | Jako HTML `placeholder` atribut vstupního pole |
| Uloží se jako hodnota? | Ne — pole zůstane `null`, vzor se zobrazí jako hint | Ne |
| Kdy zmizí | Když analytik začne psát a text přepíše | Při zahájení psaní (standardní HTML chování) |
| Vhodné použití | Vzorový obsah (příklad dobře vyplněného pole) | Nápověda k formátu nebo rozsahu vstupu |

> **Tip:** Používejte `example:` pro pole jako `root_cause`, `description`, `resolution` — všude, kde chcete ukázat, jak vypadá kvalitně vyplněný záznam. Používejte `placeholder:` pro krátké nápovědy k formátu: `"MM/RRRR"`, `"Oddělte čárkou"`, `"Např. Jan Novák"`.

---

## 10. Dědičnost šablon (`extends:`)

Šablona může dědit sekce z jiné (rodičovské) šablony pomocí klíče `extends:`. Sekce rodiče jsou vloženy PŘED sekce potomka. Dědičnost je rekurzivní — rodič může sám dědit z dalšího předka.

Abstraktní šablony (`abstract: true`) slouží výhradně jako základ pro dědičnost — nezobrazují se v dashboardu a nelze z nich přímo vytvořit záznam.

**Abstraktní základní šablona:**

```yaml
template_id: base-incident-v1
name: "Základní šablona incidentu (abstraktní základ)"
version: '1.0'
status: active
abstract: true

sections:
  - id: header
    title: Záhlaví záznamu
    type: header
    fields:
      - key: record_id
        label: ID záznamu
        auto: record_id
      - key: template_name
        label: Šablona
        auto: template_name
      - key: case_title
        label: Název incidentu
        type: text
        editable: true
        value: null
      - key: coordinator
        label: Koordinátor
        type: text
        editable: true
        value: null
      - key: created_at
        label: Datum vytvoření
        auto: now
      - key: last_saved
        label: Poslední aktualizace
        auto: last_saved
```

**Konkrétní šablona dědící ze základu:**

```yaml
template_id: incident-malware-v1
name: "Incident – Malware"
version: '1.0'
status: active
extends: base-incident-v1

meta:
  mitre_tactic: "Execution"
  mitre_technique: "T1204"

sections:
  - id: classification
    title: Klasifikace malwaru
    type: form
    fields:
      - key: malware_type
        label: Typ malwaru
        type: select
        editable: true
        options: ["Ransomware", "Trojan", "Dropper", "Cryptominer", "PUA"]
        value: null
      - key: affected_endpoint
        label: Zasažený endpoint
        type: text
        editable: true
        value: null
      - key: mitre_tactic
        label: MITRE Tactic
        type: text
        auto: meta.mitre_tactic

  - id: triage
    title: Triage postup
    type: checklist
    steps:
      - "Izoluj zasažený endpoint od sítě"
      - "Zachovej forenzní obraz před jakýmkoli zásahem"
      - "Zkontroluj logy EDR za posledních 72h"
      - "Identifikuj patient zero a vektor infekce"
```

Výsledná šablona `incident-malware-v1` bude obsahovat sekce v tomto pořadí: `header` (ze základní šablony), `classification`, `triage` (vlastní sekce).

> **Pozor:** Cyklická dědičnost (`A extends B extends A`) způsobí varování při načítání šablony a rodičovská šablona nebude nalezena. Vždy kontrolujte, že řetěz dědičnosti je acyklický.

---

## 11. Referenční tabulka všech klíčů

### Horní úroveň šablony

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `template_id` | ✓ | Unikátní ID šablony v kolekci |
| `name` | ✓ | Zobrazovaný název v UI |
| `version` | ✓ | Verze jako řetězec: `'1.0'` |
| `status` | ✓ | `active` \| `draft` \| `deprecated` |
| `sections[]` | ✓ | Seznam sekcí |
| `description` | | Popis šablony (1–2 věty) |
| `abstract` | | `true` = skrytá v dashboardu, pouze pro dědičnost |
| `extends` | | `template_id` rodičovské šablony |
| `meta{}` | | Doménové klíče přístupné přes `auto: meta.<klíč>` |
| `workflow{}` | | Přepíše workflow kolekce pro tuto šablonu |
| `workflow.initial_state` | ◐ | Počáteční stav záznamu (povinné pokud je `workflow:` přítomno) |
| `workflow.states[]` | ◐ | Seznam stavů workflow (povinné pokud je `workflow:` přítomno) |
| `workflow.states[].id` | ✓ | ID stavu (slug) |
| `workflow.states[].label` | ✓ | Zobrazovaný popis stavu |
| `workflow.states[].color` | | Bootstrap barva: `primary`, `secondary`, `success`, `danger`, `warning`, `info`, `dark` |

### Sekce (společné klíče)

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Unikátní ID sekce; auto-generované ze `title` nebo `type` pokud chybí |
| `type` | ✓ | `header` \| `form` \| `checklist` \| `table` \| `section_group` |
| `title` | ✓ | Nadpis karty |
| `hint` | | Modrý informační box nad sekcí |

### Sekce typu `form` a `header`

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `fields[]` | ✓ | Seznam polí |

### Sekce typu `checklist`

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `steps[]` | ◐ | Plochý seznam kroků (buď `steps:` nebo `step_groups:`) |
| `step_groups[]` | ◐ | Strukturované skupiny kroků |
| `step_groups[].title` | | Nadpis skupiny (`null` = bez nadpisu) |
| `step_groups[].note` | | Šedý text pod nadpisem skupiny |
| `step_groups[].hints[]` | | Seznam šedých textů pod nadpisem skupiny |
| `step_groups[].steps[]` | ✓ | Kroky skupiny |

### Krok checklistu (`step`)

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `action` | ✓ | Text kroku; alternativně jako prostý řetězec |
| `id` | | Auto-generované ze `action` nebo pozice pokud chybí |
| `done` | | Počáteční stav checkboxu (výchozí: `false`) |
| `hint` | | Šedý box s poznámkou pod krokem |
| `example` | | Vzorový text pro pole poznámky analytika |

### Sekce typu `table`

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `columns[]` | ✓ | Definice sloupců |
| `rows[]` | | Počáteční řádky vložené do záznamu při vytvoření; vynechání = prázdná tabulka (`rows: []` nepište) |
| `append_row_template{}` | | Výchozí hodnoty pro řádek přidaný uživatelem tlačítkem „+ Přidat řádek" |
| `allow_append_row` | | `true` = tlačítko pro přidání řádku |
| `allow_delete_row` | | `true` = tlačítko pro smazání řádku |
| `hints[]` | | Seznam šedých textů pod tabulkou |

### Sloupec tabulky (`column`)

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `key` | ✓ | Klíč hodnoty v řádku |
| `label` | ✓ | Nadpis sloupce |
| `type` | | `text` \| `select` \| `textarea` (výchozí: `text`) |
| `editable` | | `true` = editovatelný (výchozí: `false`) |
| `options[]` | ◐ | Povinné pokud `type: select` |

### Sekce typu `section_group`

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `sections[]` | ✓ | Podsekce (`form`, `table`, `checklist`) |
| `sections[].always_expanded` | | `true` = podsekce nelze sbalit |

### Pole formuláře

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `key` | ✓ | Unikátní klíč v rámci sekce |
| `label` | ✓ | Zobrazovaný popis |
| `type` | | `text` \| `textarea` \| `select` \| `datetime` \| `number` (výchozí: `text`) |
| `editable` | | `true` = analytik může editovat; `false` = read-only (výchozí: `true`) |
| `value` | | Počáteční hodnota (výchozí: `null`) |
| `options[]` | ◐ | Povinné pokud `type: select` |
| `auto` | | Zdroj automatické hodnoty: `record_id`, `template_name`, `template_version`, `current_user`, `now`, `last_saved`, `meta.<klíč>` |
| `example` | | Vzorová hodnota zobrazená jako šedý placeholder; resetuje se na `null` při vytvoření záznamu |
| `placeholder` | | HTML placeholder; nápověda k formátu vstupu |
| `required` | | `true` = vizuální indikátor povinného pole |
| `visible_if` | | Výraz podmíněné viditelnosti (JS, vyhodnocuje se v prohlížeči) |
| `required_if` | | Výraz podmíněné povinnosti (JS, vyhodnocuje se v prohlížeči) |
| `hint` | | Šedý text pod vstupním polem |
