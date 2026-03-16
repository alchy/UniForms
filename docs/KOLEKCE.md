# Konfigurace kolekce (collection.yaml)

Kolekce je základní organizační jednotka UniForms. Sdružuje záznamy stejného typu — například bezpečnostní incidenty, vozidla v autobazaru nebo objednávky — a definuje pro ně společné workflow, terminologii, formát ID a šablony. Každá kolekce je jeden YAML soubor; aplikace ho načte automaticky při startu a při každém požadavku.

Kolekce navíc tvoří hranici přístupových práv: uživatel vidí jen ty kolekce, ke kterým mu administrátor přidělil roli. Výjimkou je `system_admin`, který vidí všechny kolekce.

---

## Kde se kolekce ukládá

```
data/
├── collections/
│   ├── soc.yaml          ← kolekce id=soc
│   ├── autobazar.yaml    ← kolekce id=autobazar
│   └── general.yaml      ← kolekce id=general
└── schemas/
    ├── soc/              ← šablony kolekce soc
    │   ├── uib_bec_v2.yaml
    │   └── uib_malware_v2.yaml
    ├── autobazar/        ← šablony kolekce autobazar
    │   └── prijem_vozidla_v1.yaml
    └── general/          ← šablony kolekce general
        └── formular_v1.yaml
```

Výchozí cesty jsou `data/collections/` a `data/schemas/`. Obě lze změnit v Nastavení aplikace (GUI nebo API: `PATCH /api/v1/settings/`). Adresáře musí existovat — aplikace je nevytváří.

> **Poznámka:** Název souboru musí odpovídat poli `id` v YAML (bez přípony). Soubor `autobazar.yaml` musí obsahovat `id: autobazar`. Pokud pole `id` chybí, aplikace ho doplní automaticky ze jména souboru.

---

## Rychlý start

Vytvoření nové kolekce ve třech krocích:

### 1. Vytvořit YAML soubor kolekce

Ulož soubor do `data/collections/mojekolekce.yaml`:

```yaml
id: mojekolekce
name: Moje kolekce
description: Jednoduchá testovací kolekce.

workflow:
  initial_state: new
  states:
    - id: new
      label: Nové
      color: secondary
    - id: closed
      label: Uzavřeno
      color: success

id_format:
  prefix: MK
  format: "{prefix}-{YYYYMM}-{rand:04d}"

list_columns:
  - key: record_owner
    label: Zodpovědná osoba

roles:
  - id: collection_admin
    label: Správce
  - id: collection_user
    label: Uživatel

title_field: title
```

### 2. Přidat šablony

Vytvoř adresář `data/schemas/mojekolekce/` a zkopíruj do něj YAML šablony. Šablony v tomto adresáři se automaticky zobrazí při zakládání nových záznamů v dané kolekci.

### 3. Přiřadit uživatele

Přes API přiřaď uživatele do kolekce:

```bash
curl -X PATCH http://localhost:8000/api/v1/admin/collection-roles/mojekolekce \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "assignments": [
      {"username": "jan.novak", "role": "collection_admin"},
      {"username": "petra.svoboda", "role": "collection_user"}
    ]
  }'
```

Po restartu (nebo v klidu — kolekce se načítají za běhu) je kolekce dostupná.

---

## Přehled všech klíčů

### Kořenová úroveň

| Klíč | ✓ | Popis |
|------|---|-------|
| `id` | ✓ | Identifikátor kolekce; musí odpovídat názvu souboru bez přípony. Povolené znaky: `[a-z0-9_-]`. |
| `name` | ✓ | Zobrazovaný název kolekce v UI. |
| `description` | | Volný popis kolekce; zobrazuje se na stránce kolekce. |
| `terminology` | | Slovník přepisů terminologie; přepíše globální hodnoty z `uniforms.yaml`. |
| `workflow` | ✓ | Konfigurace stavů workflow (viz sekce níže). |
| `list_columns` | ✓ | Sloupce zobrazované v seznamu záznamů (viz sekce níže). |
| `id_format` | ✓ | Formát generovaných ID záznamů (viz sekce níže). |
| `roles` | ✓ | Definice rolí v kolekci (viz sekce níže). |
| `title_field` | | Klíč pole, jehož hodnota se zobrazí jako nadpis záznamu v detailu. |
| `take_over` | | Konfigurace tlačítka „Převzít" na detailu záznamu. |

```yaml
id: soc
name: "SOC – Security Operations Center"
description: >
  Kolekce UIB workbooků pro CSIRT/SOC tým.
```

---

### Sekce `workflow:`

Definuje stavy, kterými může záznam procházet — od vytvoření po uzavření.

| Klíč | ✓ | Popis |
|------|---|-------|
| `initial_state` | | ID stavu, ve kterém se vytváří nový záznam. Výchozí: `new`. |
| `states` | ✓ | Seznam stavů; každý stav je objekt s klíči `id`, `label`, `color`. |

Každý stav (`WorkflowState`):

| Klíč | ✓ | Popis |
|------|---|-------|
| `id` | ✓ | Interní identifikátor stavu; uložený v záznamu. |
| `label` | ✓ | Zobrazovaný název stavu v UI. |
| `color` | ✓ | Bootstrap barva badge/tlačítka. |

Dostupné barvy Bootstrap: `primary`, `secondary`, `success`, `danger`, `warning`, `info`, `dark`, `light`.

```yaml
workflow:
  initial_state: new
  states:
    - id: new
      label: Nové
      color: secondary
    - id: in_progress
      label: V řešení
      color: warning
    - id: on_hold
      label: Pozastaveno
      color: info
    - id: closed
      label: Uzavřeno
      color: success
```

> **Poznámka:** Stavy workflow jsou při vytvoření záznamu zkopírovány přímo do dokumentu záznamu. Změna stavů v `collection.yaml` proto neovlivní existující záznamy — ty nesou vlastní kopii stavů z doby svého vzniku.

> **Pozor:** Hodnota `initial_state` musí odpovídat `id` jednoho ze stavů v seznamu `states`. Pokud neodpovídá, záznamy se vytvoří s neplatným stavem.

---

### Sekce `id_format:`

Definuje, jak vypadají generovaná ID nových záznamů.

| Klíč | ✓ | Popis |
|------|---|-------|
| `prefix` | | Textový prefix vložený do tokenu `{prefix}`. Výchozí: `REC`. |
| `format` | | Formátovací šablona s tokeny. Výchozí: `{prefix}-{YYYYMM}-{rand:04d}`. |

Dostupné tokeny:

| Token | Popis | Příklad |
|-------|-------|---------|
| `{prefix}` | Hodnota klíče `prefix` | `UIB` |
| `{YYYYMM}` | Rok a měsíc (UTC) | `202603` |
| `{DDMMYYYY}` | Den, měsíc, rok (UTC) | `16032026` |
| `{YYYY}` | Rok čtyřmístně (UTC) | `2026` |
| `{MM}` | Měsíc dvěma číslicemi (UTC) | `03` |
| `{DD}` | Den dvěma číslicemi (UTC) | `16` |
| `{HHMM}` | Hodina a minuta (UTC) | `1423` |
| `{rand:04d}` | Náhodné celé číslo 0–9999, zarovnané na 4 místa | `0042` |
| `{rand}` | Náhodné celé číslo 0–9999, bez zarovnání | `42` |

Příklady výsledků:

| Format | Výsledek |
|--------|----------|
| `{prefix}-{YYYYMM}-{rand:04d}` | `REC-202603-0042` |
| `{prefix}-{DDMMYYYY}-{rand:04d}` | `UIB-16032026-0042` |
| `{prefix}-{YYYY}-{MM}-{rand}` | `ABZ-2026-03-42` |
| `{prefix}{HHMM}{rand:04d}` | `MK14230042` |

```yaml
id_format:
  prefix: UIB
  format: "{prefix}-{DDMMYYYY}-{rand:04d}"
```

> **Tip:** Používej `{rand:04d}` místo `{rand}` — zarovnání na čtyři místa zajistí přehledné třídění v seznamech.

---

### Sekce `list_columns:`

Definuje sloupce zobrazované v tabulce seznamu záznamů nad rámec výchozích sloupců (ID, šablona, stav, datum vytvoření).

| Klíč | ✓ | Popis |
|------|---|-------|
| `key` | ✓ | Klíč pole záznamu, jehož hodnota se zobrazí ve sloupci. |
| `label` | ✓ | Záhlaví sloupce v tabulce. |

Jak funguje vyhledávání hodnoty pole:

```
Záznam
└── data
    └── sections
        ├── section_1 (type: header)
        │   └── fields
        │       └── {key: "record_owner", value: "jan.novak"}  ← nalezeno
        ├── section_2 (type: form)
        │   └── fields
        │       └── {key: "case_title", value: "BEC útok"}    ← nalezeno
        └── section_3 (type: checklist)
            └── step_groups
                └── steps
                    └── ...
```

Aplikace prohledá všechny sekce záznamu (včetně `step_groups`) a vrátí první nalezený výskyt pole s odpovídajícím `key`. Pokud pole v záznamu neexistuje, buňka zůstane prázdná.

```yaml
list_columns:
  - key: case_title
    label: "Popis události"
  - key: record_owner
    label: "Koordinátor CSIRT"
```

> **Tip:** Jako klíče používej pole z header sekce šablony — ta jsou dostupná na všech záznamech dané kolekce.

---

### Sekce `roles:`

Definuje role, které lze uživatelům v rámci kolekce přiřadit. Aplikace rozlišuje dva pevné identifikátory rolí — jejich `label` je libovolný a zobrazuje se v UI.

| Klíč | ✓ | Popis |
|------|---|-------|
| `id` | ✓ | Identifikátor role. Povolené hodnoty: `collection_admin`, `collection_user`. |
| `label` | | Zobrazovaný název role v UI (správa uživatelů, přiřazování). Výchozí: prázdný řetězec. |

Sémantika rolí:

| id | Oprávnění |
|----|-----------|
| `collection_admin` | Správa záznamů kolekce, přiřazování uživatelů do kolekce, mazání záznamů. |
| `collection_user` | Zakládání a úprava záznamů, čtení šablon. |

```yaml
roles:
  - id: collection_admin
    label: "CSIRT Lead"
  - id: collection_user
    label: "CSIRT Analytik"
```

> **Poznámka:** Role `system_admin` je globální systémová role (nastavuje se v User Management, nikoliv v collection.yaml). `system_admin` má přístup ke všem kolekcím automaticky.

---

### Klíč `title_field`

Určuje, které pole záznamu se zobrazí jako nadpis (titulek) na stránce detailu záznamu, místo výchozího názvu šablony.

Aplikace prohledá všechny sekce záznamu (stejným způsobem jako `list_columns`) a vyhledá pole s odpovídajícím `key`. Pokud pole nenajde nebo je `title_field` nastaveno na `null`, použije se jako titulek `template_name`.

```yaml
title_field: case_title
```

> **Tip:** Nastav `title_field` na pole, které je vyplněno automaticky nebo povinně v header sekci šablony — jinak bude titulek prázdný, dokud uživatel pole nevyplní.

---

### Klíč `take_over`

Zobrazí na stránce detailu záznamu tlačítko „Převzít" (nebo jiný text dle `terminology.take_over_btn`). Po kliknutí zapíše aktuální hodnotu do určeného pole záznamu a okamžitě ho uloží.

| Klíč | ✓ | Popis |
|------|---|-------|
| `field` | ✓ | Klíč pole (v libovolné sekci záznamu), do kterého se zapíše hodnota. |
| `value_type` | | Co se do pole zapíše. Možnosti: `username` (přihlášený uživatel, výchozí), `timestamp` (aktuální čas UTC ve formátu ISO-8601). |

Pokud `take_over` chybí nebo je `null`, tlačítko se na stránce detailu nezobrazí.

```yaml
take_over:
  field: record_owner
  value_type: username
```

Příklad s časovým razítkem:

```yaml
take_over:
  field: datum_prevzeti
  value_type: timestamp
```

> **Tip:** Kombinuj `take_over` s `title_field` a `list_columns` — nastav všechny tři na stejné pole (koordinátor/zodpovědná osoba) a získáš přehledný seznam s rychlým převzetím přímo z detailu záznamu.

---

### Sekce `terminology:`

Přepíše globální terminologii z `uniforms.yaml` pouze pro tuto kolekci. Ostatní kolekce a globální UI zůstanou nezměněny.

Přepisovatelné klíče:

| Klíč | Výchozí hodnota | Popis |
|------|-----------------|-------|
| `record_id_label` | `Record ID` | Záhlaví sloupce ID v seznamu záznamů. |
| `records_subtitle` | `All records` | Podtitulek stránky seznamu záznamů. |
| `templates_subtitle` | `Available templates` | Podtitulek stránky seznamu šablon. |
| `dashboard_subtitle` | `Overview` | Podtitulek dashboardu. |
| `new_record_btn` | `New Record` | Text tlačítka pro vytvoření nového záznamu. |
| `record_owner_label` | `Record Owner` | Popisek pole vlastníka záznamu (take_over). |
| `take_over_btn` | `Take Over` | Text tlačítka Převzít. |
| `status_active` | `Active` | Název stavu šablony „aktivní". |
| `status_draft` | `Draft` | Název stavu šablony „rozpracovaná". |
| `status_deprecated` | `Deprecated` | Název stavu šablony „zrušená". |

```yaml
terminology:
  record_id_label: "ID incidentu"
  records_subtitle: "Všechny incidenty"
  templates_subtitle: "Dostupné playbooks"
  dashboard_subtitle: "Přehled incidentů"
  new_record_btn: "Nový UIB"
  record_owner_label: "Koordinátor CSIRT"
  take_over_btn: "Převzít"
  status_active: "Aktivní"
  status_draft: "Rozpracovaný"
  status_deprecated: "Zrušen"
```

> **Poznámka:** Klíče, které v `terminology:` neuvedete, zůstanou na globální hodnotě z `uniforms.yaml`. Není potřeba přepisovat vše.

---

## Nasazení kolekce přes API

Kolekce lze spravovat přes REST API bez přímého přístupu k souborovému systému. Všechny endpointy pro správu kolekcí vyžadují roli `system_admin`.

### Vytvořit novou kolekci

```bash
curl -X POST http://localhost:8000/api/v1/admin/collections/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "mojekolekce",
    "content": "id: mojekolekce\nname: Moje kolekce\n..."
  }'
```

> **Pozor:** Parametr `filename` smí obsahovat pouze malá písmena, číslice, podtržítko (`_`) a pomlčku (`-`). Při pokusu o jiný název API vrátí HTTP 400.

### Přečíst zdrojový YAML existující kolekce

```bash
curl http://localhost:8000/api/v1/admin/collections/soc/source \
  -H "Authorization: Bearer <token>"
```

### Aktualizovat YAML existující kolekce

```bash
curl -X PUT http://localhost:8000/api/v1/admin/collections/soc \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"content": "id: soc\nname: SOC updated\n..."}'
```

### Smazat kolekci

```bash
curl -X DELETE http://localhost:8000/api/v1/admin/collections/soc \
  -H "Authorization: Bearer <token>"
```

> **Pozor:** Smazání kolekce odstraní pouze konfigurační soubor `collection.yaml`. Existující záznamy a šablony v `data/schemas/soc/` zůstanou na disku nedotčeny.

### Přiřadit uživatele do kolekce

```bash
curl -X PATCH http://localhost:8000/api/v1/admin/collection-roles/soc \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "assignments": [
      {"username": "jan.novak",      "role": "collection_admin"},
      {"username": "petra.svoboda",  "role": "collection_user"},
      {"username": "tomas.cerny",    "role": "collection_user"}
    ]
  }'
```

> **Poznámka:** Endpoint `PATCH /admin/collection-roles/{collection_id}` vždy nahradí **celý** seznam přiřazení pro danou kolekci. Chceš-li uživatele odebrat, pošli seznam bez něj.

### Změnit cestu k adresáři kolekcí

```bash
curl -X PATCH http://localhost:8000/api/v1/settings/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"collections_dir": "/opt/uniforms/collections"}'
```

Povolené klíče pro `PATCH /settings/`: `records_dir`, `schemas_dir`, `collections_dir`. Zadaný adresář musí existovat.

---

## Kompletní referenční tabulka

Přehled všech klíčů konfiguračního souboru kolekce.

| Klíč | ✓ | Typ | Výchozí | Popis |
|------|---|-----|---------|-------|
| `id` | ✓ | string | — | Identifikátor; musí odpovídat názvu souboru (bez `.yaml`). |
| `name` | ✓ | string | — | Zobrazovaný název kolekce. |
| `description` | | string | `""` | Volný popis kolekce. |
| `terminology` | | dict | `{}` | Přepisy globální terminologie pro tuto kolekci. |
| `workflow.initial_state` | | string | `new` | ID počátečního stavu nových záznamů. |
| `workflow.states` | ✓ | list | (výchozí sada) | Seznam stavů workflow. |
| `workflow.states[].id` | ✓ | string | — | Interní identifikátor stavu. |
| `workflow.states[].label` | ✓ | string | — | Zobrazovaný název stavu. |
| `workflow.states[].color` | ✓ | string | `secondary` | Bootstrap barva stavu. |
| `list_columns` | ✓ | list | (record_owner) | Sloupce v seznamu záznamů. |
| `list_columns[].key` | ✓ | string | — | Klíč pole záznamu. |
| `list_columns[].label` | ✓ | string | — | Záhlaví sloupce. |
| `id_format.prefix` | | string | `REC` | Textový prefix ID. |
| `id_format.format` | | string | `{prefix}-{YYYYMM}-{rand:04d}` | Formátovací šablona ID. |
| `roles` | ✓ | list | (admin + user) | Definice rolí v kolekci. |
| `roles[].id` | ✓ | string | — | `collection_admin` nebo `collection_user`. |
| `roles[].label` | | string | `""` | Zobrazovaný název role. |
| `title_field` | | string \| null | `null` | Klíč pole pro nadpis záznamu v detailu. |
| `take_over.field` | ◐ | string | — | Klíč pole pro zápis při Převzetí. Povinný, pokud je `take_over` uveden. |
| `take_over.value_type` | | string | `username` | Co se zapíše: `username` nebo `timestamp`. |
