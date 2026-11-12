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
    ├─ 2. Knihovna bloků a dědičnost (extends:, override:, remove:, use:)
    │      Načte rodičovskou šablonu (knihovnu), rekurzivně ji vyřeší,
    │      předřadí její sekce, na místě nahradí (override) nebo vynechá
    │      (remove) jednotlivé bloky a vloží odkazované bloky (use).
    │
    └─ 3. Normalizace
           • auto: <zdroj>  →  editable: false + auto_value: <zdroj>
           • example: hodnota  →  field.value (označí is_example: true)
           • Chybějící type  →  "text"
           • type: user bez source  →  source: collection_members
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

### Validace při uložení šablony

Editor šablon (GUI) i API (`POST` / `PUT /api/v1/templates/…`) šablonu před zápisem
**zkusí načíst celou pipeline** – YAML, `template_id`, dědičnost `extends`, normalizaci
a model `UniTemplate`. Chyba vrátí `400` s popisem a soubor se nezapíše, takže
rozbitá šablona už nemůže tiše zmizet ze seznamu.

- `template_id` nelze při uložení změnit – pro nové ID vytvořte novou šablonu.
- Šablona se stejným `template_id` jako existující se nevytvoří (`409`).
- Při zakládání přes API ukládejte **nejdřív knihovnu bloků** (`abstract: true`), pak šablony, které ji používají.
- Knihovnu nelze uložit, pokud by změna přejmenovala nebo smazala blok, který jiná šablona
  upravuje (`override`), vynechává (`remove`) nebo vkládá (`use`) – viz [kapitola 10](#10-knihovny-bloků-a-dědičnost).

---

## 3. Rychlý start

> **Tip:** Šablonu lze místo psaní YAML naklikat v GUI — viz [Collection Designer](COLLECTION_DESIGNER.md). Tento dokument popisuje formát souboru, který návrhář čte a zapisuje.

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
      - key: record_owner
        label: Řešitel
        type: user
        source: collection_members

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
| `abstract` | | `true` = **knihovna bloků** – jen zdroj sekcí pro jiné šablony; nezobrazí se v seznamu šablon a nelze z ní založit záznam (výchozí: `false`) |
| `extends` | | `template_id` knihovny (v UI „Uses library"); její bloky jsou vloženy před vlastní sekce – viz [kapitola 10](#10-knihovny-bloků-a-dědičnost) |
| `meta{}` | | Libovolné doménové klíče; hodnoty jsou přístupné v polích přes `auto: meta.<klíč>` |
| `workflow{}` | | Per-šablonový override workflow kolekce (pokročilé, výjimečné). Struktura je shodná s `workflow` v konfiguraci kolekce — viz [KOLEKCE.md § workflow](KOLEKCE.md#sekce-workflow). |

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
    - key: record_owner
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
| `type` | | `text` \| `select` \| `textarea` \| `date` \| `time` \| `datetime` (výchozí: `text`); časové typy viz [kapitola 6](#6-typy-polí) |
| `editable` | | `true` = editovatelný; `false` = read-only (výchozí: `false`) |
| `options[]` | ◐ | Povinné pokud `type: select` |
| `display_tz` | | Jen `type: datetime`: `local` (výchozí) \| `utc` – pásmo, ve kterém se čas zobrazí |

Sloupce `date`, `time` a `datetime` se v nových řádcích zadávají výběrem data/času. U sloupce
`time` hlavička ukazuje „(local time)", u `datetime` pásmo zobrazení, např. „(Europe/Prague (UTC+01:00))".

```yaml
- id: feeding
  title: Krmný plán
  type: table
  allow_append_row: true
  allow_delete_row: true
  columns:
    - { key: time,   label: "Čas", type: time }       # denní čas – místní, nepřevádí se
    - { key: food,   label: "Krmivo", type: text }
    - { key: given,  label: "Podáno", type: datetime } # okamžik – ukládá se v UTC
```

---

### `section_group` — skupina sekcí

Sdružuje více logicky souvisejících sekcí pod jeden nadpis jako accordionový kontejner. Podsekce jsou libovolné typy (`form`, `table`, `checklist`). Volitelný klíč `always_expanded: true` na podsekci zabrání jejímu sbalení.

```yaml
- id: closure
  title: Uzavření incidentu
  type: section_group
  subsections:
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
| `subsections[]` | ✓ | Podsekce libovolného typu (`form`, `table`, `checklist`) |
| `subsections[].always_expanded` | | `true` = podsekce nelze sbalit |

> **Pozor:** Klíč pro podsekce je `subsections:` (ne `sections:`). Normalizátor i renderer čtou jen `subsections:` — podsekce zapsané pod `sections:` se nevykreslí. [Collection Designer](COLLECTION_DESIGNER.md) na takový zápis upozorní varováním.

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

### Časové typy — přehled

Časové typy jsou tři a liší se tím, **co** popisují. Podrobně (UTC, pásma, nastavení) viz [CAS.md](CAS.md).

| Typ | Popisuje | Uložená hodnota | Převod pásma |
|-----|----------|-----------------|:------------:|
| `datetime` | okamžik, který nastal (vylíhnutí, prohlídka) | `2026-10-13T09:04:00Z` (UTC) | ano |
| `date` | kalendářní den (datum narození) | `2026-10-13` | ne |
| `time` | denní čas, rozvrh (krmení v 07:00) | `07:00` | ne |

### `datetime` — okamžik (datum a čas)

Okamžik se **ukládá v UTC** a zobrazuje i zadává v pásmu z nastavení aplikace (Settings → Date & time).
Pod polem je značka pásma, např. „Time zone: Europe/Prague (UTC+02:00)". Klíč `display_tz: utc`
zobrazí hodnotu v UTC.

```yaml
- key: born_at
  label: Datum vylíhnutí
  type: datetime
  editable: true
  value: null
```

Výsledek: analytik vybere `13.10.2026 11:04`, uloží se `2026-10-13T09:04:00Z`. Starší hodnoty bez
pásma (`2026-10-13T11:04`) se čtou jako čas pásma z `.env` a zůstávají, dokud je nikdo nezmění.

### `date` — kalendářní den

Datum bez času. Nepřevádí se mezi pásmy – den je pro všechny stejný. Zobrazí se ve formátu ze Settings.

```yaml
- key: birth_date
  label: Datum narození
  type: date
  editable: true
  value: null
```

### `time` — denní čas

Čas dne bez data, typicky rozvrh. Ukládá se jako `HH:MM` **v místním čase a nepřevádí se** – krmení
„v 07:00" je v 07:00 v zimě i v létě. Pod polem je poznámka „Local time – not converted between time zones".

```yaml
- key: feeding_time
  label: Čas krmení
  type: time
  editable: true
  value: null
```

> **Pozor:** Pro okamžik, který skutečně nastal, použijte `datetime`, ne `date` + `time`. Jen
> `datetime` se správně přepočítá při změně letního/zimního času i při změně pásma v Settings.

### `user` — uživatel kolekce

Výběr z uživatelů, kteří mají přístup ke kolekci – **číselník stanovený aplikací**, ne volné `options`.
Seznam se načítá živě (`GET /api/v1/collections/{id}/members`) a server při uložení ověří, že
nová hodnota je platný uživatel. Typické použití je `record_owner` pro tlačítko „Převzít".

```yaml
- key: record_owner
  label: Ošetřovatel
  type: user
  source: collection_members
  hint: "Vyplní se tlačítkem Převzít péči."
```

| `source` | Nabízí |
|----------|--------|
| `collection_members` | každého s přístupem ke kolekci: system admini + role v kolekci (výchozí) |
| `collection_admin` | system admini + `collection_admin` |
| `collection_user` | jen `collection_user` |

Výsledek: pole se zobrazí jako výběr uživatelských jmen. Starší volný text (např. „Marie Krmivová")
zůstane jako volba „(not a user of this collection)"; server ho při uložení neodmítne, dokud se nezmění.

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
| `type` | | `text` \| `textarea` \| `select` \| `number` \| `datetime` \| `date` \| `time` \| `user` (výchozí: `text`) |
| `editable` | | `true` = analytik může editovat; `false` = read-only (výchozí: `true`; vždy `false` pokud je `auto:` přítomno) |
| `value` | | Počáteční hodnota (výchozí: `null`) |
| `options[]` | ◐ | Povinné pokud `type: select` |
| `source` | | Jen `type: user`: `collection_members` \| `collection_admin` \| `collection_user` (výchozí: `collection_members`) |
| `display_tz` | | Jen `type: datetime`: `local` (výchozí) \| `utc` |
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
| `now` | Čas vytvoření záznamu v UTC, např. `2026-11-12T09:39:11Z`; zobrazí se v pásmu ze Settings |
| `last_saved` | Čas posledního uložení v UTC; aktualizuje se při každém `PATCH /api/v1/records/…` |
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

## 10. Knihovny bloků a dědičnost

Víc šablon v kolekci často sdílí stejné sekce – hlavičku, identifikaci, krmný plán. Místo kopírování
je umístěte do **knihovny bloků** a šablony z ní sekce převezmou. Změna bloku v knihovně se pak
projeví ve všech šablonách, které ho používají.

| Pojem | V UI | V YAML |
|-------|------|--------|
| Šablona, ze které vznikají záznamy | Form | šablona bez `abstract` |
| Knihovna bloků | Block library | `abstract: true` |
| Blok | Building block | jedna sekce knihovny |
| Šablona používá knihovnu | Uses library | `extends: <template_id>` |

```
Knihovna (abstract: true)            Šablona (extends: knihovna)          Výsledný záznam
┌───────────────────────┐            ┌──────────────────────────┐         ┌───────────────────────┐
│ header                │──────────▶ │                          │───────▶ │ header                │
│ identification        │──────────▶ │ - remove: character      │         │ identification        │
│ character             │──────╳     │ - override: feeding  ──┐ │         │ feeding (vlastní)  ◀──┘
│ feeding               │────╳       │ - id: ostrich          │ │         │ vet_care              │
│ vet_care              │──────────▶ │ - use: ptaci#ringing ──┼─┼──────▶  │ ostrich               │
└───────────────────────┘            └──────────────────────────┘         │ ringing (z jiné knih.)│
                                                                          └───────────────────────┘
```

### Knihovna bloků (`abstract: true`)

Knihovna je obyčejná šablona s `abstract: true`. Nezobrazí se v seznamu šablon kolekce a nelze z ní
založit záznam – slouží jen jako zdroj bloků. Blokům dávejte **explicitní `id`**: šablony na ně
odkazují právě přes `id` a bez něj by se odvodilo z titulku (přejmenování titulku by odkaz rozbilo).

```yaml
template_id: zoo-zvire-base-v1
name: "Evidenční karta zvířete (základ)"
version: '1.0'
status: active
abstract: true

sections:
  - id: header
    title: Hlavička
    type: header
    fields:
      - { key: record_id, label: "Evidenční číslo", auto: record_id }
      - { key: animal_name, label: "Jméno zvířete" }
      - { key: record_owner, label: "Ošetřovatel", type: user, source: collection_members }
  - id: character
    title: Povaha a zvyky
    type: form
    fields:
      - { key: temperament, label: "Povaha", type: select, options: ["Klidná", "Zvídavá", "Panovačná"] }
  - id: feeding
    title: Krmný plán
    type: table
    allow_append_row: true
    columns:
      - { key: time, label: "Čas", type: time }
      - { key: food, label: "Krmivo", type: text }
```

### Použití knihovny (`extends:`)

Šablona s `extends: <template_id>` dostane **všechny bloky knihovny v jejich pořadí** a za nimi své
vlastní sekce. Knihovna může sama používat jinou knihovnu (řetězí se).

```yaml
template_id: zoo-pstros-v1
name: "Pštros dvouprstý"
version: '1.0'
status: active
extends: zoo-zvire-base-v1

sections:
  - id: ostrich
    title: Pštrosí specifika
    type: form
    fields:
      - { key: height_cm, label: "Výška (cm)", type: number }
```

Výsledek: záznam pštrosa má sekce `header`, `character`, `feeding`, `ostrich`.

> **Poznámka:** Vlastní sekce se stejným `id` jako blok knihovny blok **nenahradí** – přidá druhou
> sekci (zpětná kompatibilita). Návrhář na to upozorní. K nahrazení slouží `override:`.

### Úprava bloku jen pro jednu šablonu (`override:`)

Položka `override: <id bloku>` nahradí blok knihovny **celou** vlastní sekcí, na jeho původním místě.
Ostatní šablony dál používají verzi z knihovny. V UI „Customize for this form only".

```yaml
sections:
  - override: feeding
    title: Krmný plán (pštros)
    type: table
    allow_append_row: true
    columns:
      - { key: time, label: "Čas", type: time }
      - { key: food, label: "Krmivo", type: text }
      - { key: grams, label: "Dávka (g)", type: text }
```

Výsledek: pštros má na třetím místě vlastní „Krmný plán (pštros)". Pozdější změny bloku `feeding`
v knihovně se ho už netýkají.

### Vynechání bloku (`remove:`)

`- remove: <id bloku>` blok knihovny v této šabloně nepoužije. Položka nesmí mít další klíče.
V UI „Remove from this form" (vrátit lze „Restore").

```yaml
sections:
  - remove: character
```

### Vložení jednoho bloku (`use:`)

`- use: <template_id>#<id bloku>` vloží jeden blok z libovolné knihovny kolekce jako **živý odkaz** –
obsah se při každém načtení bere z knihovny. Funguje i bez `extends`. Volitelné `id:` blok přejmenuje
(potřeba, když stejný blok vkládáte dvakrát). V UI paleta „Building blocks (shared)".

```yaml
sections:
  - use: zoo-ptaci-bloky-v1#ringing
  - use: zoo-ptaci-bloky-v1#ringing
    id: ringing_second
```

### Náhrada bloku jiným (`override:` + `use:`)

Kombinace nahradí blok knihovny jiným sdíleným blokem, na stejném místě. Výsledná sekce si ponechá
`id` nahrazeného bloku. V UI „Replace…".

```yaml
sections:
  - override: vet_care
    use: zoo-ptaci-bloky-v1#vet_birds
```

### Pravidla

| Pravidlo | Chování |
|----------|---------|
| Pořadí | bloky knihovny (s `override`/`remove` na místě) → ostatní položky šablony v zapsaném pořadí |
| Id bloku | `id`, jinak slug z `title`, jinak z `type` – stejné pravidlo pro resolver i návrhář |
| `override` | nahrazuje celou sekci, neslučuje po polích |
| `use` | smí odkazovat jen na blok **definovaný** v dané šabloně, ne na blok, který ona sama dědí nebo vkládá |
| Cyklus | `extends` i `use` hlídají cykly; cyklická větev se přeskočí a zaloguje |
| Chybný odkaz | návrhář i API ho odmítnou při uložení; za běhu se položka přeskočí s varováním v logu |
| Ochrana knihovny | knihovnu nelze uložit, pokud by změna smazala/přejmenovala blok, který někdo upravuje, vynechává nebo vkládá |
| Záznamy | záznam si ukládá výsledné sekce (bez `override`/`remove`/`use`); změna knihovny se projeví jen u **nových** záznamů |

| Klíč položky v `sections` | ✓ | Popis |
|---------------------------|:-:|-------|
| `override` | | `id` bloku knihovny, který tato sekce nahradí (sekce pak musí mít `type` a obsah, nebo `use`) |
| `remove` | | `id` bloku knihovny, který se vynechá; položka nesmí mít další klíče |
| `use` | | `<template_id>#<id bloku>` – vložený blok; s `override` nahrazuje blok knihovny |
| `id` | | U `use`: nové id vloženého bloku |

> **Pozor:** Cyklická dědičnost (`A extends B extends A`) i odkaz `use` na vlastní šablonu jsou
> chybou. Návrhář je označí a resolver cyklickou větev ignoruje.

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
| `abstract` | | `true` = knihovna bloků; skrytá v seznamu šablon, nelze z ní založit záznam |
| `extends` | | `template_id` knihovny bloků („Uses library") |
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
| `override` | | Nahradí blok knihovny s tímto `id` (viz kapitola 10) |
| `remove` | | Vynechá blok knihovny s tímto `id`; samostatná položka |
| `use` | | Vloží blok `<template_id>#<id>`; s `override` blok nahradí |

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
| `type` | | `text` \| `select` \| `textarea` \| `date` \| `time` \| `datetime` (výchozí: `text`) |
| `editable` | | `true` = editovatelný (výchozí: `false`) |
| `options[]` | ◐ | Povinné pokud `type: select` |
| `display_tz` | | Jen `type: datetime`: `local` \| `utc` |

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
| `type` | | `text` \| `textarea` \| `select` \| `number` \| `datetime` \| `date` \| `time` \| `user` (výchozí: `text`) |
| `editable` | | `true` = analytik může editovat; `false` = read-only (výchozí: `true`) |
| `value` | | Počáteční hodnota (výchozí: `null`) |
| `options[]` | ◐ | Povinné pokud `type: select` |
| `source` | | Jen `type: user`: `collection_members` \| `collection_admin` \| `collection_user` |
| `display_tz` | | Jen `type: datetime`: `local` \| `utc` |
| `auto` | | Zdroj automatické hodnoty: `record_id`, `template_name`, `template_version`, `current_user`, `now`, `last_saved`, `meta.<klíč>` |
| `example` | | Vzorová hodnota zobrazená jako šedý placeholder; resetuje se na `null` při vytvoření záznamu |
| `placeholder` | | HTML placeholder; nápověda k formátu vstupu |
| `required` | | `true` = vizuální indikátor povinného pole |
| `visible_if` | | Výraz podmíněné viditelnosti (JS, vyhodnocuje se v prohlížeči) |
| `required_if` | | Výraz podmíněné povinnosti (JS, vyhodnocuje se v prohlížeči) |
| `hint` | | Šedý text pod vstupním polem |
