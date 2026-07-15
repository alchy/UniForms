# Tvůj první formulář za 10 minut

Tento návod tě provede od čerstvě nainstalované aplikace k prvnímu vyplněnému záznamu. Poskládá dohromady tři samostatné části — **kolekci**, **šablonu** a **záznam** — ve správném pořadí. Detailní referenci každé části najdeš v [KOLEKCE.md](KOLEKCE.md) a [SABLONY.md](SABLONY.md); tady jde o nejkratší funkční cestu.

Jako příklad postavíme jednoduchý IT helpdesk.

## Než začneš

Aplikace musí běžet a musíš být přihlášen jako admin — viz [INSTALACE.md](INSTALACE.md). Ve zkratce:

```bash
python start.py          # běží na http://localhost:8080
```

Přihlaš se jako `admin` / `admin` (nebo podle svého `.env`).

## Jak to do sebe zapadá

```
kolekce (data/collections/helpdesk.yaml)   ← organizační jednotka: workflow, ID, sloupce
   └── šablony (data/schemas/helpdesk/*.yaml) ← struktura formuláře (sekce, pole)
          └── záznamy (data/records/helpdesk/*.json) ← vyplněná data, generují se za běhu
```

Kolekce musí existovat dřív než šablona, šablona dřív než záznam. Přístup ke kolekci je řízen rolí — `system_admin` (náš admin) má přístup ke všem kolekcím automaticky.

## Krok 1 — Vytvoř kolekci

**V UI:** pravý horní roh → **Admin → Collections → New**, do editoru vlož YAML níže, ulož pod názvem `helpdesk`.

Vznikne soubor `data/collections/helpdesk.yaml`:

```yaml
id: helpdesk           # musí odpovídat názvu souboru (bez .yaml)
name: IT Helpdesk
description: Požadavky na IT podporu.

workflow:
  initial_state: new
  states:
    - { id: new,         label: "Nový",     color: secondary }
    - { id: in_progress, label: "V řešení",  color: warning }
    - { id: closed,      label: "Uzavřeno",  color: success }

id_format:
  prefix: TKT
  format: "{prefix}-{YYYYMM}-{rand:04d}"   # → TKT-202607-0042

list_columns:
  - { key: title,        label: "Název požadavku" }
  - { key: record_owner, label: "Řešitel" }

title_field: title       # které pole tvoří nadpis záznamu
```

> Kolekce se načítají za běhu — po uložení je hned k dispozici, restart není potřeba.

## Krok 2 — Přidej šablonu

**V UI:** otevři kolekci → **Templates → New**, vlož YAML níže, ulož jako `zakladni`.

Vznikne soubor `data/schemas/helpdesk/zakladni.yaml`:

```yaml
template_id: helpdesk-zakladni-v1
name: "Helpdesk – základní požadavek"
version: "1.0"
status: active            # 'active' = nabízí se při zakládání záznamu

sections:
  - id: header
    title: Hlavička
    type: header
    fields:
      - { key: record_id, label: "ID záznamu", auto: record_id }   # auto = vyplní server
      - { key: title,     label: "Název požadavku", placeholder: "např.: Tiskárna offline" }
      - { key: record_owner, label: "Řešitel" }

  - id: details
    title: Podrobnosti
    type: form
    fields:
      - key: priority
        label: Priorita
        type: select
        options: ["Nízká", "Střední", "Vysoká"]
      - { key: description, label: "Popis problému", type: textarea }

  - id: postup
    title: Postup řešení
    type: checklist
    steps:
      - "Potvrď přijetí a kontaktuj zadatele."
      - "Prozkoumej příčinu."
      - "Aplikuj opravu a uzavři záznam."
```

Klíč `auto: record_id` znamená, že pole vyplní server (nedá se editovat). Celý katalog typů sekcí a polí je v [SABLONY.md](SABLONY.md).

## Krok 3 — Vytvoř záznam

V UI otevři kolekci **IT Helpdesk**, přejdi na **Šablony** a u šablony „Helpdesk – základní požadavek" klikni na **Nový záznam**. Aplikace:

1. vygeneruje ID (`TKT-202607-0042`),
2. vyplní automatická pole (`record_id`),
3. otevře záznam k editaci a zamkne ho pro tebe.

Vyplň *Název požadavku*, *Prioritu* a *Popis*, odškrtej kroky a klikni **Uložit**. Záznam se uloží jako `data/records/helpdesk/TKT-202607-0042.json`. Zpět na seznamu ho uvidíš i s workflow stavem a sloupci definovanými v kolekci.

## Krok 4 (volitelný) — Pusti k tomu kolegu

Admin vidí vše, ale běžný uživatel potřebuje roli v kolekci. Vytvoř uživatele (**Admin → Users → New**) a přiřaď mu roli — buď v UI na kartě uživatele, nebo přes API:

```bash
# přihlášení uloží cookie
curl -s -c cookies.txt -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  http://localhost:8080/api/v1/auth/login

# role v kolekci: collection_admin (správa šablon) nebo collection_user (jen záznamy)
curl -s -b cookies.txt -X PATCH -H "Content-Type: application/json" \
  -d '{"assignments":[{"username":"jan.novak","role":"collection_user"}]}' \
  http://localhost:8080/api/v1/admin/collection-roles/helpdesk
```

## Co dál

| Chci… | Kde |
|-------|-----|
| Víc typů polí, tabulky, podmíněnou viditelnost, dědičnost šablon | [SABLONY.md](SABLONY.md) |
| Vlastní workflow, terminologii, tlačítko „Převzít", sloupce seznamu | [KOLEKCE.md](KOLEKCE.md) |
| Role, přihlášení, auth providery | [AUTENTIZACE.md](AUTENTIZACE.md) |
| Vlastní typ sekce (JS renderer) | [FRONTEND.md](FRONTEND.md), sekce 9 |
| Vložit UniForms do vlastní aplikace | [KNIHOVNA.md](KNIHOVNA.md) |
