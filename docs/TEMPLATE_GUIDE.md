# Template Reference Guide — Schema v2

Tento dokument je technická reference pro vývojáře a pokročilé autory šablon. Popisuje celé schéma šablony v2, pipeline normalizace, všechny typy sekcí a jejich klíče.

Průvodce pro autory bez technického zázemí: [TEMPLATE_AUTHORING.md](TEMPLATE_AUTHORING.md).

---

## Jak to funguje

```
data/schemas/{collection_id}/nazev-v1.yaml   — soubor šablony (read-only zdroj)
      │
      │  Backend — načtení šablony (template_service.py):
      │  1. Parsování YAML → Python dict
      │  2. Normalizace:
      │     • Doplnění výchozích hodnot polí (type, editable, value)
      │     • Rozvoj auto: shorthand → editable: false + auto_value: <source>
      │     • Flat steps: [] → step_groups s title: null
      │     • Auto-generování chybějících id ze slug nadpisu
      │  3. Vyhodnocení dědičnosti (extends:) — sekce rodiče prepend
      │
      │  Backend — vytvoření záznamu (record_service.py):
      │  4. Hluboká kopie normalizované šablony
      │  5. example: → is_example: true + value/analyst_note
      │  6. Vyplnění auto_value polí (record_id, current_user, now…)
      ▼
data/records/{collection_id}/REC-ID.json   — záznam (šablona se nemění)
      │
      │  Frontend: UniForms.render(sections, container)
      ▼
Prohlížeč — interaktivní formulář
```

Šablona je read-only vzor. Každý záznam je nezávislá hluboká kopie. Soubory šablon nikdy neobsahují uživatelská data.

---

## Rychlý start — kompletní šablona se všemi typy sekcí

Zkopírujte a uložte jako `data/schemas/helpdesk/helpdesk-kompletni-v1.yaml`.

```yaml
template_id: helpdesk-kompletni-v1
name: Helpdesk — kompletní šablona
version: '1.0'
status: draft
description: Ukázková šablona demonstrující všechny typy sekcí v2.
meta:
  sla_hodiny: 8

sections:
  - id: header
    title: Hlavička
    type: header
    fields:
      - key: title
        label: Název požadavku
        hint: Krátký popis viditelný v seznamu záznamů.
        placeholder: 'např.: Tiskárna offline – budova B'
      - key: coordinator
        label: Řešitel
      - key: record_id
        label: ID záznamu
        auto: record_id
      - key: template_name
        label: Šablona
        auto: template_name
      - key: template_version
        label: Verze
        auto: template_version

  - id: kontext
    title: Kontext požadavku
    type: section_group
    subsections:
      - id: spolecna-data
        type: form
        title: Společná data
        always_expanded: true
        fields:
          - key: source
            label: Zdroj požadavku
            type: select
            options: [Email, Telefon, Portál, Monitoring]
          - key: environment
            label: Prostředí
            type: select
            options: [Produkce, Staging, Vývoj, Test]
      - id: dotcene-systemy
        type: table
        title: Dotčené systémy
        always_expanded: true
        columns:
          - key: name
            label: Název
          - key: type
            label: Typ
            type: select
            options: [Server, Stanice, Účet, Aplikace]
            editable: true
        rows: []

  - id: podrobnosti
    title: Podrobnosti požadavku
    type: form
    hint: Vyplňte před předáním řešiteli.
    fields:
      - key: priority
        label: Priorita
        type: select
        options: [Nízká, Střední, Vysoká, Kritická]
      - key: description
        label: Popis problému
        type: textarea
        example: Uživatel nemůže tisknout od dnešního rána. Tiskárna hlásí chybu "offline".
      - key: impact
        label: Dopad na provoz
        type: textarea
        visible_if: "priority == 'Vysoká' || priority == 'Kritická'"
        required_if: "priority == 'Kritická'"
      - key: reported_at
        label: Nahlášeno
        type: datetime

  - id: postup
    title: Postup řešení
    type: checklist
    step_groups:
      - title: 1. Diagnostika
        note: cíl 15 minut
        hints:
          - Zkontrolujte logy před kontaktováním uživatele.
        steps:
          - Reprodukujte problém v testovacím prostředí.
          - action: Zkontrolujte poslední změny v systému.
            example: 'Poslední patch KB5034441 aplikován 2026-03-01'
      - title: 2. Řešení
        steps:
          - Aplikujte opravu nebo obejití.
          - Ověřte opravu s uživatelem.
      - title: 3. Uzavření
        steps:
          - Zdokumentujte příčinu a přijatá opatření.
          - Uzavřete záznam a informujte zadatele.

  - id: akcni-body
    title: Akční body
    type: table
    allow_append: true
    allow_delete: true
    columns:
      - key: action
        label: Akce
      - key: owner
        label: Řešitel
      - key: due_date
        label: Termín
      - key: status
        label: Stav
        type: select
        options: [Čeká, Probíhá, Hotovo, N/A]
        editable: true
    rows:
      - action: Počáteční vyšetřování
        owner: ''
        due_date: ''
        status: Čeká

  - id: zaver
    title: Uzavření
    type: form
    fields:
      - key: resolution_type
        label: Způsob řešení
        type: select
        options: [Opraveno, Obejití, Chyba uživatele, Duplicita, Nelze reprodukovat]
      - key: root_cause
        label: Kořenová příčina
        type: textarea
      - key: resolution
        label: Popis řešení
        type: textarea
      - key: closed_at
        label: Uzavřeno
        type: datetime
      - key: last_saved
        label: Naposledy uloženo
        auto: last_saved
```

---

## Struktura souboru — top-level klíče

```yaml
template_id: helpdesk-v1        # povinný, unikátní v rámci kolekce
name: Helpdesk Request          # povinný
version: '1.0'                  # povinný — vždy jako řetězec
status: active                  # active | draft | deprecated
description: Popis sablony.     # volitelný
extends: base-request-v1        # volitelný — dědičnost
abstract: false                 # true = základní šablona, nezobrazí se v seznamu
meta: {}                        # libovolné klíče, dostupné přes auto: meta.<key>
sections: []                    # povinný — seznam sekcí
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `template_id` | ✓ | Unikátní identifikátor v rámci kolekce; slug formát `nazev-v1` |
| `name` | ✓ | Zobrazovaný název v UI |
| `version` | ✓ | Verze šablony jako řetězec, např. `'1.0'` nebo `'2.3'` |
| `status` | ✓ | `active` \| `draft` \| `deprecated` |
| `sections` | ✓ | Seznam objektů sekcí |
| `description` | | Účel šablony, 1–2 věty |
| `extends` | | `template_id` rodičovské šablony |
| `abstract` | | `true` = šablona nezobrazena v nabídce vytvoření záznamu |
| `meta` | | Slovník libovolných klíčů dostupných přes `auto: meta.<klic>` |

---

## Normalizace — shorthand syntax

Normalizace probíhá při načítání šablony. Stávající hodnoty se nikdy nepřepisují — normalizace používá výhradně `setdefault()`. Plná i zkrácená syntaxe jsou plně zpětně kompatibilní.

### Výchozí hodnoty polí

| Klíč | Výchozí | Poznámka |
|------|---------|----------|
| `type` | `text` | Vynechte pro jednořádkové textové vstupy |
| `editable` | `true` | Vynechte pro editovatelná pole |
| `value` | `null` | Vynechte pro prázdná pole |

```yaml
# Plná syntaxe
- key: reporter_name
  label: Nahlásil
  type: text
  editable: true
  value: null

# Zkrácená syntaxe (ekvivalent)
- key: reporter_name
  label: Nahlásil
```

### `auto:` shorthand

`auto: <source>` je zkratka za `editable: false` + `auto_value: <source>`.

```yaml
# Zkrácená syntaxe
- key: record_id
  label: ID záznamu
  auto: record_id

# Plná syntaxe (ekvivalent)
- key: record_id
  label: ID záznamu
  editable: false
  auto_value: record_id
```

### Flat `steps:` → `step_groups`

Pokud sekce `checklist` obsahuje `steps:` (plochý seznam) místo `step_groups:`, normalizér automaticky zabalí kroky do jedné skupiny s `title: null`.

```yaml
# Zkrácená syntaxe
steps:
  - Potvrďte přijetí.
  - Prozkoumejte příčinu.

# Výsledek po normalizaci
step_groups:
  - title: null
    steps:
      - action: Potvrďte přijetí.
        done: false
        analyst_note: null
      - action: Prozkoumejte příčinu.
        done: false
        analyst_note: null
```

### Auto-generování ID

Sekce, skupiny kroků a kroky bez explicitního `id` dostanou automaticky generované ID ze slugu jejich `title` (nebo `type`). Explicitní `id` zadávejte jen tehdy, kdy potřebujete stabilní referenci.

---

## Typy sekcí

### `header`

Povinná první sekce každé šablony. Editovatelná pole jsou zobrazena prominentně; read-only pole (s `auto:` nebo `editable: false`) jsou zobrazena jako kompaktní informační mřížka.

```yaml
- id: header
  title: Hlavička
  type: header
  fields:
    - key: title
      label: Název požadavku
      hint: Krátký popis viditelný v seznamu záznamů.
      placeholder: 'např.: Tiskárna offline – budova B'
    - key: coordinator
      label: Řešitel
    - key: record_id
      label: ID záznamu
      auto: record_id
    - key: template_name
      label: Šablona
      auto: template_name
    - key: template_version
      label: Verze šablony
      auto: template_version
    - key: current_user
      label: Vytvořil
      auto: current_user
    - key: last_saved
      label: Naposledy uloženo
      auto: last_saved
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce (auto-generovaný, pokud chybí) |
| `type` | ✓ | `header` |
| `title` | ✓ | Nadpis karty |
| `fields[]` | ✓ | Seznam polí; read-only pole zobrazena jako info mřížka |

---

### `form`

Formulářová sekce s dvousloupcovou mřížkou polí. Volitelný klíč `hint` zobrazí modrý informační box nad formulářem. Pole podporují `visible_if`, `required_if`, `placeholder`, `example`.

```yaml
- id: podrobnosti
  title: Podrobnosti požadavku
  type: form
  hint: Vyplňte před předáním řešiteli.
  fields:
    - key: priority
      label: Priorita
      type: select
      options: [Nízká, Střední, Vysoká, Kritická]
    - key: description
      label: Popis problému
      type: textarea
      placeholder: Popište problém stručně a srozumitelně.
    - key: impact
      label: Dopad na provoz
      type: textarea
      visible_if: "priority == 'Vysoká' || priority == 'Kritická'"
      required_if: "priority == 'Kritická'"
    - key: reported_at
      label: Nahlášeno
      type: datetime
    - key: reporter
      label: Nahlásil
      example: Jana Nováková, odd. Finance
    - key: resolution_type
      label: Způsob řešení
      type: select
      options: [Opraveno, Obejití, Chyba uživatele, Duplicita]
      visible_if: "priority != null"
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce |
| `type` | ✓ | `form` |
| `title` | ✓ | Nadpis karty |
| `fields[]` | ✓ | Seznam polí |
| `hint` | | Modrý informační box nad formulářem |

---

### `checklist`

Sekce s kroky, které uživatel průběžně odškrtává a přidává poznámky. Podporuje plochý seznam (`steps:`) nebo skupiny kroků (`step_groups:`).

**Plochý seznam kroků:**

```yaml
- id: postup-flat
  title: Rychlý postup
  type: checklist
  steps:
    - Potvrďte přijetí požadavku a kontaktujte zadatele.
    - Prozkoumejte příčinu.
    - action: Eskalujte, pokud nelze vyřešit do SLA.
      hint: Postup eskalace viz interní wiki.
    - Aplikujte opravu nebo řešení.
    - Ověřte řešení se zadatelem.
```

**Skupiny kroků:**

```yaml
- id: postup-skupiny
  title: Postup řešení
  type: checklist
  step_groups:
    - title: 1. Diagnostika
      note: cíl 15 minut
      hints:
        - Zkontrolujte logy před kontaktováním uživatele.
      steps:
        - Reprodukujte problém v testovacím prostředí.
        - action: Zkontrolujte poslední změny v systému.
          example: 'Poslední patch KB5034441 aplikován 2026-03-01'
    - title: 2. Řešení
      steps:
        - Aplikujte opravu.
        - Ověřte opravu s uživatelem.
    - title: 3. Uzavření
      steps:
        - Zdokumentujte příčinu a přijatá opatření.
        - Uzavřete záznam a informujte zadatele.
```

#### Klíče sekce `checklist`

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce |
| `type` | ✓ | `checklist` |
| `title` | ✓ | Nadpis karty |
| `steps[]` | ◐ | Plochý seznam kroků; buď `steps:` nebo `step_groups:` |
| `step_groups[]` | ◐ | Seznam skupin kroků; buď `steps:` nebo `step_groups:` |

#### Klíče skupiny kroků (`step_groups[]`)

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `title` | ✓ | Nadpis skupiny |
| `steps[]` | ✓ | Kroky v této skupině |
| `id` | | Identifikátor skupiny (auto-generovaný ze slugu `title`) |
| `note` | | Šedý podnázev za nadpisem skupiny |
| `hints[]` | | Pole řetězců — provozní poznámky zobrazené jako šedé boxy |

#### Klíče kroku (`steps[]`)

Krok lze zapsat jako prostý řetězec nebo jako slovník:

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `action` | ✓ | Text instrukce (povinný pouze ve slovníkové syntaxi) |
| `id` | | Identifikátor kroku (auto-generovaný, pokud chybí) |
| `done` | | Počáteční stav zaškrtávátka; výchozí `false` |
| `analyst_note` | | Předvyplněná poznámka; výchozí `null` |
| `hint` | | Provozní nápověda zobrazená pod krokem |
| `example` | | Vzorová poznámka; normalizér rozbalí na `is_example: true` + `analyst_note` |

---

### `table`

Univerzální tabulka. Sloupce jsou definovány jako seznam slovníků. Podporuje přidávání a mazání řádků uživatelem.

```yaml
- id: akcni-body
  title: Akční body
  type: table
  allow_append: true
  allow_delete: true
  columns:
    - key: action
      label: Akce
    - key: owner
      label: Řešitel
    - key: due_date
      label: Termín
    - key: status
      label: Stav
      type: select
      options: [Čeká, Probíhá, Hotovo, N/A]
      editable: true
  rows:
    - action: Počáteční vyšetřování
      owner: ''
      due_date: ''
      status: Čeká
    - action: Informovat zadatele
      owner: ''
      due_date: ''
      status: Čeká
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce |
| `type` | ✓ | `table` |
| `title` | ✓ | Nadpis karty |
| `columns[]` | ✓ | Seznam definic sloupců (slovníky s `key`, `label` a volitelně `type`, `options`, `editable`) |
| `rows[]` | ✓ | Předvyplněné řádky; prázdná tabulka: `rows: []` |
| `allow_append` | | `true` = uživatel může přidávat řádky |
| `allow_delete` | | `true` = uživatel může mazat řádky |

#### Klíče definice sloupce (`columns[]`)

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `key` | ✓ | Klíč sloupce; musí odpovídat klíčům v `rows[]` |
| `label` | ✓ | Zobrazovaný název záhlaví sloupce |
| `type` | | Typ vstupu v buňce; `text` (výchozí) nebo `select` |
| `options[]` | ◐ | Povinné pokud `type: select`; seznam možností |
| `editable` | | `true` = buňky tohoto sloupce jsou editovatelné; výchozí `false` |

---

### `section_group`

Accordionový kontejner seskupující více podsekci. Podporované typy podsekci: `form` a `table`.

```yaml
- id: kontext
  title: Kontext požadavku
  type: section_group
  subsections:
    - id: spolecna-data
      type: form
      title: Společná data
      always_expanded: true
      fields:
        - key: source
          label: Zdroj požadavku
          type: select
          options: [Email, Telefon, Portál, Monitoring]
        - key: environment
          label: Prostředí
          type: select
          options: [Produkce, Staging, Vývoj, Test]
    - id: dotcene-systemy
      type: table
      title: Dotčené systémy
      always_expanded: true
      columns:
        - key: name
          label: Název
        - key: type
          label: Typ
          type: select
          options: [Server, Stanice, Účet, Aplikace]
          editable: true
        - key: owner
          label: Správce
      rows: []
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce |
| `type` | ✓ | `section_group` |
| `title` | ✓ | Nadpis karty |
| `subsections[]` | ✓ | Seznam podsekci; každá je `form` nebo `table` |
| `subsections[].id` | | Identifikátor podsekce |
| `subsections[].type` | ✓ | `form` nebo `table` |
| `subsections[].title` | ✓ | Nadpis accordionového panelu |
| `subsections[].always_expanded` | | `true` = panel nelze sbalit |

---

## Typy polí a jejich klíče

Pole jsou používána v sekcích `header`, `form` a v `form` podsekci uvnitř `section_group`.

### Všechny klíče pole

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `key` | ✓ | Unikátní identifikátor pole v rámci sekce |
| `label` | ✓ | Zobrazovaný popisek v UI |
| `type` | | Typ vstupu; výchozí `text` (viz tabulka níže) |
| `editable` | | `true` = uživatel může editovat; `false` = read-only; výchozí `true` |
| `value` | | Výchozí hodnota; `null` = prázdné |
| `hint` | | Nápověda zobrazená pod popiskem pole |
| `placeholder` | | HTML `placeholder` atribut; nikdy se neukládá |
| `example` | | Vzorová hodnota; normalizér rozbalí na `is_example: true` + `value` |
| `auto` | | Zkratka za `editable: false` + `auto_value: <source>` |
| `auto_value` | | Zdroj pro automatické vyplnění při vytvoření záznamu |
| `options[]` | ◐ | Povinné pokud `type: select`; seznam možností |
| `visible_if` | | Výraz; pole se zobrazí jen pokud podmínka platí |
| `required_if` | | Výraz; pole je označeno jako povinné pokud podmínka platí |

### Typy polí

| `type` | Widget | Popis |
|--------|--------|-------|
| `text` | `<input type="text">` | Jednořádkový textový vstup (výchozí) |
| `textarea` | `<textarea>` | Víceřádkový textový vstup |
| `select` | `<select>` | Výběr z předdefinovaného seznamu; vyžaduje `options:` |
| `datetime` | `<input type="datetime-local">` | Datum a čas |

---

## `auto:` shorthand — tabulka zdrojů

| Hodnota | Vyplní se |
|---------|-----------|
| `record_id` | Vygenerované ID záznamu (např. `REC-202603-0001`) |
| `template_name` | `name` ze šablony |
| `template_version` | `version` ze šablony |
| `current_user` | Přihlášený uživatel při vytvoření záznamu |
| `now` | Aktuální čas při vytvoření záznamu |
| `last_saved` | Čas posledního uložení; aktualizuje se při každém uložení |
| `meta.<klic>` | Hodnota z `meta:` bloku šablony, např. `meta.sla_hodiny` |

> Pole s `auto: last_saved` (nebo `auto_value: last_saved`) se aktualizuje při **každém** uložení záznamu. Časová zóna je čtena z klíče `TIMEZONE` v `.env`; výchozí je `UTC`.

---

## `visible_if` a `required_if`

Výrazy vyhodnocované v JavaScriptu na straně klienta při každé změně hodnoty pole v sekci.

### Syntaxe

| Výraz | Popis |
|-------|-------|
| `field_key == 'hodnota'` | Striktní rovnost |
| `field_key != 'hodnota'` | Striktní nerovnost |
| `field_key == null` | Pole je prázdné (null nebo prázdný řetězec) |
| `field_key != null` | Pole je vyplněno |
| `výraz && výraz` | Logické AND |
| `výraz \|\| výraz` | Logické OR |

### Příklady

```yaml
# Zobrazit pole jen při vysoké nebo kritické prioritě
- key: impact
  label: Dopad na provoz
  type: textarea
  visible_if: "priority == 'Vysoká' || priority == 'Kritická'"

# Povinné pouze při kritické prioritě
- key: escalation_reason
  label: Důvod eskalace
  type: textarea
  required_if: "priority == 'Kritická'"

# Zobrazit, pokud je jakákoliv hodnota vyplněna
- key: notes
  label: Poznámky
  type: textarea
  visible_if: "resolution_type != null"

# Kombinace podmínek
- key: vendor_ticket
  label: Tiket u dodavatele
  visible_if: "category == 'Hardware' && priority == 'Kritická'"
```

> `visible_if` a `required_if` pracují s hodnotami polí v rámci téže sekce (nebo podsekce). Odkaz na pole z jiné sekce není podporován.

---

## `example:` a `placeholder:`

### `example:`

Vzorová hodnota. Normalizér při načtení šablony rozbalí `example:` na `is_example: true` + `value` (u polí) nebo `analyst_note` (u kroků). Při klonování šablony do záznamu se vzorová hodnota přesune do klíče `example` v JSON záznamu, kde ji frontend zobrazí jako šedý placeholder. Uživatel ji přepisem nahradí vlastním textem.

```yaml
# Pole formuláře
- key: root_cause
  label: Kořenová příčina
  type: textarea
  example: Heslo uživatele vypršelo a způsobilo výpadek přihlášení na třech systémech.

# Krok checklistu
- action: Zdokumentujte posloupnost událostí.
  example: '09:14 — přijata výstraha · 09:22 — kontaktován uživatel · 09:47 — reprodukován problém'
```

### `placeholder:`

Nápověda zobrazená jako HTML atribut `placeholder` vstupního pole. Nikdy se neukládá jako hodnota záznamu. Zobrazuje se jako světle šedý text uvnitř prázdného pole.

```yaml
- key: title
  label: Název požadavku
  placeholder: 'např.: Tiskárna offline – budova B'
```

### Srovnání

| | `example:` | `placeholder:` |
|--|-----------|----------------|
| Kde se zobrazí | Šedý text v poli záznamu (po klonování) | HTML `placeholder` atribut |
| Uloží se? | Ne (`is_example: true`) | Ne |
| Zmizí při editaci? | Ano — přepsáním | Ano — po zadání jakéhokoliv znaku |
| Použití v krocích | Ano (`analyst_note`) | Ne |

---

## `meta:` namespace

Blok `meta:` na top-level šablony slouží k uložení libovolných metadat specifických pro doménu nebo rozšíření. Hodnoty jsou přístupné přes `auto: meta.<klic>` v polích.

```yaml
template_id: helpdesk-v1
name: Helpdesk Request
version: '1.0'
status: active
meta:
  sla_hodiny: 8
  kategorie_itsm: request
  zodpovedny_tym: IT Support L1

sections:
  - id: header
    title: Hlavička
    type: header
    fields:
      - key: title
        label: Název
      - key: sla_info
        label: SLA
        auto: meta.sla_hodiny
```

---

## Dědičnost šablon

### `extends:`

Šablona s klíčem `extends` zdědí všechny sekce rodičovské šablony. Sekce rodiče jsou vloženy PŘED sekce potomka. Normalizace a dědičnost jsou aplikovány od nejhlubšího rodiče nahoru.

```yaml
template_id: helpdesk-premium-v1
name: Helpdesk — premium požadavek
extends: helpdesk-zakladni-v1
version: '1.0'
status: active
sections:
  - id: sla
    type: form
    title: SLA sledování
    fields:
      - key: sla_deadline
        label: SLA termín
        type: datetime
      - key: sla_tier
        label: Úroveň SLA
        type: select
        options: [Bronze, Silver, Gold, Platinum]
```

### `abstract: true`

Abstraktní šablona slouží výhradně jako základ pro dědičnost. Nezobrazuje se v nabídce pro vytvoření záznamu. Musí mít `status: active`, aby ji bylo možné použít jako rodiče.

```yaml
template_id: base-request-v1
name: Základní požadavek (abstraktní)
abstract: true
status: active
sections:
  - id: header
    title: Hlavička
    type: header
    fields:
      - key: title
        label: Název
        placeholder: Stručný název požadavku.
      - key: coordinator
        label: Řešitel
      - key: record_id
        label: ID záznamu
        auto: record_id
```

---

## Kolekce a workflow

Příslušnost šablony ke kolekci je dána **umístěním souboru** v adresářové struktuře `data/schemas/{collection_id}/`. V souboru šablony samotné žádný klíč `collection:` neexistuje.

Workflow (stavy záznamu jako `open`, `in_progress`, `resolved`) je definováno **výhradně v definici kolekce** — šablony si workflow nedefinují. Kolekce také definuje terminologii (jak se říká záznamům a šablonám).

Viz `data/collections/{id}.yaml` a dokumentaci COLLECTIONS.md (připravujeme).

---

## Reference — souhrn všech klíčů

### Top-level klíče šablony

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `template_id` | ✓ | Unikátní identifikátor v rámci kolekce |
| `name` | ✓ | Zobrazovaný název v UI |
| `version` | ✓ | Verze šablony jako řetězec |
| `status` | ✓ | `active` \| `draft` \| `deprecated` |
| `sections` | ✓ | Seznam sekcí |
| `description` | | Popis účelu šablony |
| `extends` | | `template_id` rodičovské šablony |
| `abstract` | | `true` = nezobrazí se v nabídce vytvoření záznamu |
| `meta` | | Slovník libovolných klíčů |

### Klíče sekce (společné)

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce (auto-generovaný ze slugu `title`) |
| `type` | ✓ | Typ sekce: `header`, `form`, `checklist`, `table`, `section_group` |
| `title` | ✓ | Nadpis karty |

### Klíče pole (fields[])

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `key` | ✓ | Unikátní identifikátor pole v sekci |
| `label` | ✓ | Popisek pole |
| `type` | | `text` (výchozí) \| `textarea` \| `select` \| `datetime` |
| `editable` | | `true` (výchozí) \| `false` |
| `value` | | Výchozí hodnota; výchozí `null` |
| `hint` | | Nápověda pod popiskem |
| `placeholder` | | HTML `placeholder`; nikdy se neukládá |
| `example` | | Vzorová hodnota; zobrazí se jako šedý placeholder v záznamu |
| `auto` | | Zkratka za `editable: false` + `auto_value:` |
| `auto_value` | | Zdroj automatické hodnoty |
| `options[]` | ◐ | Povinné pro `type: select` |
| `visible_if` | | Podmíněná viditelnost |
| `required_if` | | Podmíněná povinnost |

### Klíče sloupce tabulky (columns[])

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `key` | ✓ | Identifikátor sloupce |
| `label` | ✓ | Záhlaví sloupce |
| `type` | | `text` (výchozí) \| `select` |
| `options[]` | ◐ | Povinné pro `type: select` |
| `editable` | | `true` = buňky editovatelné; výchozí `false` |

### Klíče skupiny kroků (step_groups[])

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `title` | ✓ | Nadpis skupiny |
| `steps[]` | ✓ | Kroky v této skupině |
| `id` | | Identifikátor skupiny |
| `note` | | Šedý podnázev |
| `hints[]` | | Provozní poznámky |

### Klíče kroku (steps[])

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `action` | ✓ | Text instrukce (povinný ve slovníkové syntaxi) |
| `id` | | Identifikátor kroku |
| `done` | | Výchozí stav zaškrtávátka; výchozí `false` |
| `analyst_note` | | Předvyplněná poznámka; výchozí `null` |
| `hint` | | Nápověda pod krokem |
| `example` | | Vzorová poznámka |

### Zdroje `auto_value`

| Hodnota | Vyplní se |
|---------|-----------|
| `record_id` | ID záznamu |
| `template_name` | `name` ze šablony |
| `template_version` | `version` ze šablony |
| `current_user` | Přihlášený uživatel |
| `now` | Čas vytvoření záznamu |
| `last_saved` | Čas posledního uložení (aktualizuje se při každém uložení) |
| `meta.<klic>` | Hodnota z `meta:` bloku šablony |
