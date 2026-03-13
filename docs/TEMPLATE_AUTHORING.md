# Průvodce tvorbou šablon

Tento průvodce je určen autorům šablon — lidem, kteří navrhují strukturu záznamů v systému UniForms. Ke čtení ani psaní šablon nepotřebujete znalost programování. Šablona je prostý textový soubor ve formátu YAML.

Po přečtení tohoto průvodce budete schopni vytvořit, uložit a aktivovat vlastní šablonu.

Technická reference pro vývojáře a pokročilé autory: [TEMPLATE_GUIDE.md](TEMPLATE_GUIDE.md).

---

## Co je šablona a proč ji vytvářet?

Šablona definuje strukturu jednoho typu záznamu: jaké sekce obsahuje, jaká pole se v každé sekci zobrazují a jaké kroky má uživatel splnit. Když někdo vytvoří nový záznam, systém zkopíruje šablonu do čistého dokumentu a uložení — obsah šablony samotné se nikdy nemění.

Vlastní šablona zajistí, že:
- Každý záznam daného typu začíná se správnou strukturou.
- Uživatelé nezapomenou vyplnit důležitá pole ani přeskočit klíčové kroky.
- Noví členové týmu okamžitě vidí, co a jak se dokumentuje.
- Každý krok je zaznamenán a auditovatelný.

---

## Jak to funguje?

```
Soubor YAML (šablona)
      │
      │  Systém při vytváření záznamu:
      │  1. Načte a zvaliduje YAML
      │  2. Hluboce zkopíruje strukturu
      │  3. Doplní automatické hodnoty (ID záznamu, čas, uživatel…)
      ▼
Nový záznam (JSON dokument)
      │
      │  Prohlížeč:
      │  Zobrazí sekce a pole jako interaktivní formulář
      ▼
Analytik/uživatel vyplní a uloží záznam
```

Šablona je vzor — nikdy neobsahuje data zadaná uživatelem.

---

## Rychlý start

Níže je kompletní minimální šablona pro helpdesk požadavek. Zkopírujte ji, uložte jako `data/schemas/helpdesk/helpdesk-zakladni-v1.yaml` a otestujte.

```yaml
template_id: helpdesk-zakladni-v1
name: Helpdesk — základní požadavek
version: '1.0'
status: draft
description: Základní šablona pro IT helpdesk požadavky.

sections:
  - id: header
    title: Hlavička
    type: header
    fields:
      - key: title
        label: Název požadavku
        placeholder: 'např.: Tiskárna offline – budova B'
      - key: coordinator
        label: Řešitel
      - key: record_id
        label: ID záznamu
        auto: record_id
      - key: template_name
        label: Šablona
        auto: template_name

  - id: details
    title: Podrobnosti
    type: form
    fields:
      - key: priority
        label: Priorita
        type: select
        options: [Nízká, Střední, Vysoká, Kritická]
      - key: description
        label: Popis problému
        type: textarea
        placeholder: Popište problém stručně a srozumitelně.

  - id: reseni
    title: Postup řešení
    type: checklist
    steps:
      - Potvrďte přijetí požadavku a kontaktujte zadatele.
      - Prozkoumejte příčinu.
      - Aplikujte opravu nebo řešení.
      - Ověřte řešení se zadatelem a uzavřete záznam.

  - id: zaver
    title: Uzavření
    type: form
    fields:
      - key: resolution
        label: Popis řešení
        type: textarea
      - key: closed_at
        label: Uzavřeno
        type: datetime
```

Po uložení souboru přejděte v aplikaci na **Šablony** — šablona se zobrazí se stavem `draft`. Vytvořte testovací záznam, projděte všechny sekce a ověřte, že vše vypadá správně. Pak změňte `status` na `active`.

---

## Kde ukládat soubory

Každá šablona patří do kolekce. Kolekce je skupina šablon stejné povahy (např. helpdesk, správa incidentů, evidence zařízení).

```
data/
  schemas/
    helpdesk/              ← ID kolekce
      zakladni-v1.yaml
      premium-v1.yaml
    evidence-zarizeni/
      server-v1.yaml
      stanice-v1.yaml
```

**Příslušnost šablony ke kolekci je dána umístěním souboru** — žádný klíč `collection:` v YAML šablony neexistuje. Soubor umístěný do `data/schemas/helpdesk/` automaticky patří do kolekce `helpdesk`.

Jmenná konvence souboru: `nazev-v{cislo}.yaml` (malá písmena bez diakritiky, pomlčky místo mezer).

---

## 3-krokový proces vytvoření šablony

### Krok 1 — Zkopírujte existující šablonu

Nejjednodušší start je zkopírovat existující šablonu podobného typu a upravit ji. Pokud žádná vhodná neexistuje, použijte minimální příklad z oddílu Rychlý start výše.

```
helpdesk-zakladni-v1.yaml  →  helpdesk-premium-v1.yaml
```

### Krok 2 — Upravte soubor

Otevřete soubor v libovolném textovém editoru (VS Code, Notepad++ apod.). Upravte:
- Metadata šablony (viz níže).
- Sekce a pole specifická pro tento typ záznamu.
- Kroky checklistu odpovídající skutečnému postupu.

> Při editaci YAML dbejte na odsazení — každá úroveň jsou 2 mezery. Nikdy nemixujte mezery a tabulátory.

### Krok 3 — Otestujte šablonu

V aplikaci přejděte na **Šablony** a vytvořte testovací záznam. Projděte všechny sekce, vyplňte pole, odškrtněte kroky checklistu. Pokud vše funguje správně, změňte `status` z `draft` na `active`. Testovací záznamy smažte — tato funkce je dostupná administrátorům v seznamu záznamů.

---

## Metadata šablony

Každý soubor šablony začíná blokem metadat (tzv. top-level klíče). Tyto klíče popisují šablonu jako celek a jsou povinné nebo volitelné.

```yaml
template_id: helpdesk-zakladni-v1
name: Helpdesk — základní požadavek
version: '1.0'
status: draft
description: Standardní šablona pro IT helpdesk požadavky prvního stupně.
extends: base-request-v1
abstract: false
meta:
  sla_hodiny: 8
sections: []
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `template_id` | ✓ | Unikátní identifikátor v rámci kolekce; formát `nazev-v1` (malá písmena, pomlčky) |
| `name` | ✓ | Zobrazovaný název v aplikaci |
| `version` | ✓ | Verze šablony — vždy jako řetězec, např. `'1.0'` |
| `status` | ✓ | `draft` \| `active` \| `deprecated`; nové šablony začínají jako `draft` |
| `sections` | ✓ | Seznam sekcí šablony |
| `description` | | 1–2 věty popisující účel šablony a cílovou skupinu |
| `extends` | | `template_id` rodičovské šablony pro dědičnost sekcí |
| `abstract` | | `true` = šablona slouží pouze jako rodič, nezobrazí se v nabídce pro vytvoření záznamu |
| `meta` | | Libovolné klíče dostupné přes `auto: meta.<klic>` v polích |

> Verzi vždy uzavřete do jednoduchých uvozovek: `version: '1.0'`. Bez uvozovek by YAML `1.0` interpretoval jako číslo a dojde k chybě.

---

## Přehled typů sekcí

Šablona se skládá ze sekcí. Každá sekce má klíč `type`, který určuje, jak se zobrazí.

| Typ | Kdy použít |
|-----|------------|
| `header` | Vždy první sekce — název záznamu, řešitel, automatická pole (ID, šablona) |
| `form` | Libovolná pole k vyplnění; podporuje podmíněná pole a nápovědy |
| `checklist` | Postup krok za krokem; uživatel kroky odškrtává a přidává poznámky |
| `table` | Tabulka s řádky (akční body, dotčené systémy, kontakty…) |
| `section_group` | Accordion skládající více podsekci do jednoho panelu |

### Doporučené pořadí sekcí

```
header → form (kontext/podrobnosti) → section_group (složitější data)
       → checklist (postup) → table (akční body) → form (uzavření)
```

---

## Detaily sekcí

### `header` — hlavičková sekce

Povinná první sekce každé šablony. Zobrazuje klíčové informace záznamu: název, řešitele a automaticky vyplněná pole jako ID záznamu nebo jméno šablony.

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
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce (auto-generovaný, pokud chybí) |
| `type` | ✓ | `header` |
| `title` | ✓ | Nadpis karty |
| `fields[]` | ✓ | Seznam polí |

---

### `form` — formulářová sekce

Dvousloupcová mřížka s libovolnými poli. Volitelný klíč `hint` zobrazí modré informační pole nad formulářem. Pole mohou být podmíněně viditelná nebo povinná.

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
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce |
| `type` | ✓ | `form` |
| `title` | ✓ | Nadpis karty |
| `fields[]` | ✓ | Seznam polí |
| `hint` | | Modrý informační box nad formulářem |

---

### `checklist` — kontrolní seznam

Sekce s kroky, které uživatel průběžně odškrtává a přidává k nim poznámky. Kroky lze zapsat jako prostý seznam (`steps:`) nebo ve skupinách (`step_groups:`).

**Plochý seznam kroků** (jednodušší, bez skupin):

```yaml
- id: postup
  title: Postup řešení
  type: checklist
  steps:
    - Potvrďte přijetí požadavku a kontaktujte zadatele.
    - Prozkoumejte příčinu.
    - action: Eskalujte, pokud nelze vyřešit do SLA.
      hint: Zkontrolujte eskalační matici v interní wiki.
    - Aplikujte opravu nebo řešení.
    - Ověřte řešení se zadatelem.
```

**Skupiny kroků** (pro složitější postupy):

```yaml
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
        - action: Zkontrolujte poslední změny.
          example: 'Poslední patch KB5034441 aplikován 2026-03-01'
    - title: 2. Řešení
      steps:
        - Aplikujte opravu.
        - Ověřte opravu s uživatelem.
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce |
| `type` | ✓ | `checklist` |
| `title` | ✓ | Nadpis karty |
| `steps[]` | ◐ | Plochý seznam kroků; použijte, pokud nepotřebujete skupiny |
| `step_groups[]` | ◐ | Seznam skupin kroků; buď `steps:` nebo `step_groups:` |

> Buď `steps:` nebo `step_groups:` — ne obě najednou. Pokud použijete `steps:`, systém automaticky vytvoří jednu skupinu bez nadpisu.

---

### `table` — tabulka

Univerzální tabulka pro akční body, dotčené systémy, kontakty nebo jiné tabulkové záznamy. Sloupce jsou definovány jako seznam slovníků s klíčem `key` a `label`.

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

---

### `section_group` — accordionový kontejner

Seskupuje více podsekci do jednoho skládacího panelu. Vhodné pro šablony s rozsáhlým kontextovým blokem, který nechcete zobrazovat vždy rozbalený.

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
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `id` | | Identifikátor sekce |
| `type` | ✓ | `section_group` |
| `title` | ✓ | Nadpis karty |
| `subsections[]` | ✓ | Seznam podsekci (typ `form` nebo `table`) |
| `subsections[].always_expanded` | | `true` = panel nelze sbalit |

---

## Psaní checklistu

### Plochý seznam kroků

Jednoduchý krok (bez nápověd nebo příkladů) napište jako prostý řetězec:

```yaml
steps:
  - Potvrďte přijetí požadavku.
  - Zkontrolujte poslední systémové změny.
  - Prozkoumejte otevřené související tikety.
```

Pro krok s příkladem nebo nápovědou použijte slovníkovou syntaxi:

```yaml
steps:
  - action: Zdokumentujte chybovou zprávu přesně tak, jak se zobrazila.
    example: 'Error 0x80070005: Access Denied at C:\Windows\System32\...'
  - action: Eskalujte na L2, pokud nelze vyřešit do 4 hodin.
    hint: Postup eskalace najdete v interní wiki pod heslem "SLA matice".
```

### Skupiny kroků

Skupiny kroků (`step_groups:`) použijte, když má postup logicky oddělené fáze:

```yaml
step_groups:
  - title: 1. Diagnostika
    note: cíl 15 minut
    hints:
      - Nejprve zkontrolujte logy — ušetří to čas při hovoru s uživatelem.
    steps:
      - Reprodukujte problém v testovacím prostředí.
      - Zkontrolujte poslední změny v produkci.
  - title: 2. Řešení
    steps:
      - Aplikujte opravu nebo obejití (workaround).
      - Ověřte opravu přímo s uživatelem.
  - title: 3. Uzavření
    steps:
      - Zdokumentujte příčinu a přijatá opatření.
      - Uzavřete záznam a informujte zadatele.
```

### Pravidla pro kroky

- `action` — instrukce ve formě "co má uživatel udělat"
- `hint` — provozní poznámka nebo varování zobrazené pod krokem (šedý box)
- `example` — vzorová poznámka, která se zobrazí jako šedý placeholder v poli pro poznámku ke kroku
- `id` pole pro kroky a skupiny jsou volitelná — systém je generuje automaticky

---

## Mechanismus `example:` a `placeholder:`

Tyto dva klíče vypadají podobně, ale fungují odlišně.

### `example:`

Vzorová hodnota. Po vytvoření záznamu se zobrazí jako šedý placeholder v poli nebo v poli pro poznámku ke kroku. Uživatel ji přepisem nahradí vlastním textem — tím vzorový text zmizí.

```yaml
# V poli formuláře
- key: root_cause
  label: Kořenová příčina
  type: textarea
  example: Heslo uživatele vypršelo a způsobilo výpadek přihlášení na třech systémech.

# V kroku checklistu
- action: Zdokumentujte posloupnost událostí.
  example: '09:14 — přijata výstraha · 09:22 — kontaktován uživatel · 09:47 — reprodukován problém'
```

Použití: `root_cause`, `resolution`, `description`, kroky checklistu — všude, kde chcete ukázat, jak vypadá dobře vyplněné pole.

### `placeholder:`

Nápověda zobrazená přímo v HTML atributu `placeholder` vstupního pole. Nikdy se neuloží jako hodnota. Zobrazuje se jako světle šedý text uvnitř prázdného pole.

```yaml
- key: title
  label: Název požadavku
  placeholder: 'např.: Tiskárna offline – budova B'
```

Použití: krátký příklad formátu nebo obsahu, který má uživatel zadat.

| | `example:` | `placeholder:` |
|--|-----------|----------------|
| Kde se zobrazí | Jako šedý placeholder v poli záznamu | Jako HTML `placeholder` atribut |
| Uloží se? | Ne (je označeno jako vzor) | Ne |
| Použití | Vzorový obsah k přepsání | Nápověda k formátu vstupu |

---

## Podmíněná pole

Klíče `visible_if` a `required_if` umožňují zobrazit pole nebo označit je jako povinná v závislosti na hodnotě jiného pole.

### `visible_if` — podmíněná viditelnost

```yaml
- key: impact
  label: Dopad na provoz
  type: textarea
  visible_if: "priority == 'Vysoká' || priority == 'Kritická'"
```

Pole `impact` se zobrazí pouze tehdy, když je `priority` rovna `Vysoká` nebo `Kritická`.

### `required_if` — podmíněná povinnost

```yaml
- key: escalation_reason
  label: Důvod eskalace
  type: textarea
  required_if: "priority == 'Kritická'"
```

### Podporované výrazy

| Výraz | Popis |
|-------|-------|
| `field == 'hodnota'` | Pole se rovná hodnotě |
| `field != 'hodnota'` | Pole se nerovná hodnotě |
| `field == null` | Pole je prázdné |
| `field != null` | Pole je vyplněno |
| `výraz && výraz` | Obě podmínky musí platit |
| `výraz \|\| výraz` | Alespoň jedna podmínka musí platit |

> `visible_if` a `required_if` pracují s hodnotami polí v rámci téže sekce. Odkaz na pole z jiné sekce není podporován.

---

## Dědičnost šablon

Šablona může dědit sekce z rodičovské šablony pomocí klíče `extends`. Sekce rodiče jsou vloženy PŘED sekce potomka.

```yaml
template_id: helpdesk-premium-v1
name: Helpdesk — premium požadavek
extends: helpdesk-zakladni-v1
version: '1.0'
status: draft
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

Výsledná šablona bude mít nejprve všechny sekce ze šablony `helpdesk-zakladni-v1` a za nimi sekci `sla`.

### Abstraktní šablona

Abstraktní šablona slouží výhradně jako základ pro dědičnost — uživatelům se nezobrazuje v nabídce pro vytvoření záznamu.

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
      - key: coordinator
        label: Řešitel
      - key: record_id
        label: ID záznamu
        auto: record_id
```

---

## Checklist před aktivací

Než změníte `status` z `draft` na `active`, ověřte:

- `template_id` je unikátní — zkontrolujte ostatní soubory v `data/schemas/{collection_id}/`
- `name`, `description` jsou srozumitelné a vystihují účel šablony
- Sekce `header` je první sekcí a obsahuje pole `title`
- Kroky checklistu jsou v logickém pořadí a odpovídají skutečnému postupu
- Všechna důležitá pole pro uzavření záznamu jsou ve finální `form` sekci
- Byl vytvořen testovací záznam a všechny sekce se zobrazily správně
- Testovací záznamy byly smazány

---

## Časté YAML chyby

### Odsazení

YAML je citlivý na odsazení. Každá úroveň jsou 2 mezery. Nikdy nemixujte mezery a tabulátory.

```yaml
# SPRÁVNĚ
sections:
  - id: header
    type: header
    fields:
      - key: title
        label: Název

# ŠPATNĚ — nekonzistentní odsazení
sections:
 - id: header
    type: header
```

### Speciální znaky v hodnotách

Pokud hodnota obsahuje dvojtečku, uvozovky nebo začíná speciálním znakem, uzavřete ji do jednoduchých nebo dvojitých uvozovek:

```yaml
hint: 'Časová osa: do 1h · do 24h · do 72h'
example: "Tiket #2025-112"
placeholder: 'např.: Server nedostupný – budova A'
```

### Verzování

Při výrazné změně existující šablony vytvořte nový soubor (`helpdesk-zakladni-v2.yaml`) a starý soubor označte jako `deprecated`. Záznamy vytvořené ze staré šablony zůstanou plně funkční.

```yaml
# Starý soubor
status: deprecated

# Nový soubor
template_id: helpdesk-zakladni-v2
version: '2.0'
status: active
```

### Verze jako řetězec

Hodnotu `version` vždy uzavřete do uvozovek:

```yaml
version: '1.0'   # správně — řetězec
version: 1.0     # špatně — YAML to zparsuje jako číslo
```
