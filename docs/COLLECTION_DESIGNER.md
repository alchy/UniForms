# Collection Designer

Collection Designer je webový návrhář, ve kterém `system_admin` vytváří a upravuje kolekce a jejich šablony formulářů myší a vyplňováním atributů — bez psaní YAML. Dokument je určen administrátorům, kteří s návrhářem pracují, a vývojářům, kteří chtějí stejné funkce volat z vlastního kódu nebo přes API.

YAML soubory zůstávají jedinou definicí (`data/collections/<id>.yaml`, `data/schemas/<kolekce>/*.yaml`). Návrhář je čte a zapisuje; nic dalšího si neukládá. Formát souborů popisují [KOLEKCE.md](KOLEKCE.md) a [SABLONY.md](SABLONY.md).

---

## Co to je a k čemu slouží?

Dosud se kolekce a šablony upravovaly v editoru surového YAML (Admin → Collections, Templates → Edit). To vyžaduje znát klíče, odsazení a pravidla formátu. Collection Designer nabízí totéž jako formulář:

- **průvodce kolekcí** v šesti krocích — základ, stavy workflow, záznamy (formát ID, sloupce seznamu, titulek, převzetí), role a terminologie, šablony, kontrola a uložení,
- **návrhář šablony** — paleta objektů (sekce, pole, sloupce, kroky), plátno formuláře s přetahováním, panel atributů vybraného objektu, živý náhled a zobrazení výsledného YAML.

Editory surového YAML zůstávají a návrhář na ně odkazuje. Hodí se pro věci, které návrhář neumí (viz [Omezení](#omezení)), a pro soubory s komentáři, o které nechceš přijít.

Stránka je v menu **Admin → Collection Designer** (`/admin/designer`) a vidí ji jen `system_admin`. Ostatní přístupová práva se nemění.

---

## Jak to funguje?

Návrhář nepracuje s textem YAML, ale s **modelem** — slovníkem, který vznikne načtením YAML souboru. Model se **nenormalizuje**: zkratky (`auto:`, `example:`, plochý `steps:`) i klíče, pro které návrhář nemá ovládací prvek, v něm zůstávají tak, jak jsou v souboru. Díky tomu se při uložení neztratí nic, co návrhář nezná.

```
data/schemas/zoo/zoo_pstros_v1.yaml
    │
    ▼  designer_service.load_template()        yaml.safe_load, bez normalizace
model (dict)  +  source {hash, comments, …}
    │
    ▼  GET /api/v1/admin/designer/collections/zoo/templates/zoo-pstros-v1
prohlížeč: designer_model.js upravuje model
    │        (přidání, přesun, smazání, změna atributu)
    │
    ├─ POST …/check-template   → nálezy, náhled sekcí, YAML   (nic nezapisuje)
    │
    ▼  PUT …/templates/zoo-pstros-v1   {model, base_hash, confirm_rewrite}
designer_service.save_template()
    │
    ├─ 1. lint návrháře + TemplateService._validate()   (chyba → 422, nic se nezapíše)
    ├─ 2. model == obsah souboru?  → "unchanged", soubor se nepřepisuje
    ├─ 3. base_hash nesedí?        → 409 stale (soubor se mezitím změnil)
    ├─ 4. ztratily by se komentáře a chybí confirm_rewrite?  → 409 rewrite_not_confirmed
    ├─ 5. záloha do .designer_backup/
    └─ 6. zápis kanonického YAML
```

Server je jediná autorita: prohlížeč jen posílá model, validuje a zapisuje server. Zápisy jdou přes `/api/v1`, takže je zaznamená [auditní stopa](AUDIT.md).

---

## Rychlý start

Nová kolekce s jednou šablonou, bez jediného řádku YAML:

1. Přihlas se jako `system_admin` a otevři **Admin → Collection Designer**.
2. Klikni **New collection**. V kroku *Basics* vyplň název — ID se navrhne samo (např. `IT Helpdesk` → `it-helpdesk`).
3. Projdi kroky tlačítkem **Next**. Výchozí hodnoty (tři stavy, formát ID, role) jsou platné; uprav jen to, co potřebuješ.
4. V kroku *Review & save* zkontroluj nálezy a YAML a klikni **Create collection**.
5. Otevře se krok *Templates*. Klikni **New template**, vyplň název a potvrď **Start designing**.
6. Z palety přetáhni na plátno sekci **Form** a do ní pole. Klikem na objekt se vpravo zobrazí jeho atributy.
7. Přepni na **Preview**, zkontroluj formulář a klikni **Save template**.

Šablona je hned dostupná v *Templates* dané kolekce; nový záznam z ní vytvoříš tlačítkem *New record*.

> **Tip:** Nová šablona začíná ve stavu `draft`. Až ji ověříš, přepni v atributech šablony *Status* na `active`.

---

## Krok za krokem

### Průvodce kolekcí

| Krok | Co nastavuješ | Klíče v YAML |
|------|---------------|--------------|
| Basics | název, ID, popis | `id`, `name`, `description` |
| Workflow | stavy, jejich pořadí, barvy, počáteční stav | `workflow.states`, `workflow.initial_state` |
| Records | prefix a formát ID, sloupce seznamu, pole titulku, tlačítko Převzít | `id_format`, `list_columns`, `title_field`, `take_over` |
| Roles & terms | názvy dvou rolí kolekce, přepisy terminologie | `roles`, `terminology` |
| Templates | seznam šablon kolekce, otevření návrháře šablony | soubory v `data/schemas/<id>/` |
| Review & save | kontrola serverem, výsledný YAML, uložení | — |

Změny v krocích se drží jen v prohlížeči, dokud je v posledním kroku neuložíš. Krok *Templates* je u nové kolekce zamčený, dokud kolekce neexistuje — šablony se ukládají do jejího adresáře.

ID kolekce nelze po vytvoření změnit: je to název souboru a klíč, podle kterého se párují role uživatelů.

> **Poznámka:** Řádky stavů a sloupců lze přeřadit tažením za úchyt vlevo nebo šipkami. U klíčů sloupců, titulku a pole pro převzetí návrhář napovídá klíče polí nalezené v šablonách kolekce a upozorní, když klíč v žádné šabloně není.

### Návrhář šablony

Obrazovka má tři části:

| Část | K čemu slouží |
|------|---------------|
| Paleta (vlevo) | Objekty k vložení: sekce, pole, sloupce tabulky, skupiny a kroky checklistu. |
| Plátno (uprostřed) | Struktura šablony. Nahoře karta šablony, pod ní zděděné sekce (jen pro čtení) a vlastní sekce. |
| Atributy (vpravo) | Vlastnosti vybraného objektu a akce: posun nahoru/dolů, duplikace, smazání. |

Objekt vložíš **přetažením** z palety na plátno, nebo **kliknutím** — vloží se k právě vybranému objektu. Existující objekty lze přetahovat v rámci sekce i mezi sekcemi. Plátno dovolí jen smysluplné umístění:

| Objekt | Kam ho lze umístit |
|--------|--------------------|
| sekce `header`, `section_group` | jen na nejvyšší úroveň |
| sekce `form`, `table`, `checklist` | na nejvyšší úroveň nebo do `section_group` |
| pole | do sekce `header` nebo `form` |
| sloupec | do sekce `table` |
| skupina kroků | do sekce `checklist` |
| krok | do checklistu bez skupin, nebo do skupiny kroků |

Pod plátnem běží průběžná kontrola serverem (chyby a varování s cestou k objektu). Přepínač **Live preview below** zobrazí pod návrhem náhled, který se obnovuje při každé změně; záložka **Preview** ukáže náhled přes celou šířku a **YAML** výsledný soubor. Náhled kreslí stejný renderer jako detail záznamu (`UniForms.render`), včetně zděděných sekcí.

Tlačítko **Undo** vrací poslední změny (až 60 kroků). Šablona se zapíše až tlačítkem **Save template**.

> **Pozor:** `template_id` nelze po prvním uložení změnit. Pro jiné ID vytvoř novou šablonu.

### Dědičnost šablon

V dialogu nové šablony (nebo v atributech šablony) zvol *Extends*. Sekce rodiče se na plátně zobrazí šedě nad vlastními sekcemi a upravují se v rodičovské šabloně. Rodič musí existovat — nejdřív ulož rodiče (typicky `abstract`), potom potomka.

---

## Přehled konceptů

### Model

Model je slovník odpovídající YAML souboru jedna ku jedné. Server ho vrací a přijímá jako JSON.

```json
{
  "template_id": "helpdesk-request-v1",
  "name": "Helpdesk request",
  "version": "1.0",
  "status": "draft",
  "sections": [
    {
      "id": "header", "title": "Header", "type": "header",
      "fields": [
        {"key": "record_id", "label": "Record ID", "auto": "record_id"},
        {"key": "title", "label": "Title"}
      ]
    }
  ]
}
```

| Vlastnost | Důsledek |
|-----------|----------|
| nenormalizovaný | `auto:` zůstane `auto:`, plochý `steps:` zůstane plochý, textový krok zůstane textem |
| neznámé klíče se zachovají | `mitre_tactic`, `option_hints`, `classification_hints`… návrhář jen zobrazí jako *Other attributes* |
| pořadí klíčů se drží | výsledný YAML má klíče ve stejném pořadí jako původní soubor |
| zapisuje se jen potřebné | výchozí hodnota (např. `type: text`) se do souboru nepřidává, pokud tam nebyla |

### Zachování ručně psaného YAML

PyYAML neumí zachovat komentáře ani původní formátování. Návrhář proto soubor chrání čtyřmi způsoby:

```
uložení beze změny obsahu      → soubor se vůbec nepřepíše (komentáře zůstávají)
změna + soubor s komentáři     → 409 rewrite_not_confirmed, GUI se zeptá
potvrzený přepis               → úvodní blok komentářů se zachová,
                                 původní soubor jde do .designer_backup/
soubor se mezitím změnil       → 409 stale (kontrola base_hash)
```

| Pojem | Význam |
|-------|--------|
| `source.comments` | počet řádků s komentářem v souboru |
| `source.comments_lost` | komentáře, které by přepis zahodil (všechny kromě úvodního bloku) |
| `source.anchors` | YAML kotvy a aliasy; přepis je rozbalí |
| `source.canonical` | soubor už je ve formátu návrháře — další uložení nic neztratí |
| `source.rewrite_lossy` | uložení změny vyžaduje `confirm_rewrite: true` |
| `.designer_backup/` | adresář vedle souboru; drží posledních 10 verzí každého souboru |

Soubor s hodnotou, kterou nelze bezpečně přenést přes JSON (datum bez uvozovek, neřetězcový klíč), návrhář neotevře a odkáže na editor surového YAML (`422 unsupported`).

> **Tip:** Před prvním použitím návrháře na ručně psaných definicích spusť `python scripts/check_designer_roundtrip.py`. Skript nic nezapisuje a pro každý soubor ověří, že přepis nezmění jeho obsah, a vypíše, kolik komentářů by se ztratilo.

### Kontrola a validace

Platí stejná pravidla jako v editorech YAML — návrhář volá tytéž funkce — a navíc vlastní lint se srozumitelnějšími hláškami.

| Vrstva | Co hlídá | Výsledek |
|--------|----------|----------|
| `parse_collection_yaml` | YAML, `id` = název souboru, `initial_state` mezi stavy, model `CollectionConfig` | chyba, `422` |
| `TemplateService._validate` / `save` / `create` | `template_id`, dědičnost, normalizace, model `UniTemplate`, neměnnost ID, slug názvu souboru | chyba, `422` |
| lint kolekce | název, unikátní ID stavů, povolené role, klíče sloupců | chyba |
| lint kolekce | neznámý token formátu ID, klíč pole, který v šablonách není | varování |
| lint šablony | `template_id`, název, verze jako text, existence rodiče a cyklus dědičnosti, klíč pole/sloupce | chyba |
| lint šablony | select bez voleb, duplicitní klíč, podmínka na neexistující pole, `sections` místo `subsections` | varování |

Chyby brání uložení, varování ne. Každý nález nese cestu k objektu (`sections[2].fields[1]`).

### Audit

Každé uložení z návrháře je zápis přes `/api/v1`, a tedy auditní událost. Návrhář do ní doplňuje identifikátory — nikdy obsah.

```json
{
  "t": "2026-11-11T11:50:11+00:00",
  "kind": "write",
  "op": "designer_update_template",
  "actor": "user:admin",
  "method": "PUT",
  "path": "/api/v1/admin/designer/collections/soc/templates/uib-bec-v2",
  "collection_id": "soc",
  "template_id": "uib-bec-v2",
  "status": 200,
  "outcome": "ok",
  "via": "designer",
  "change": "updated",
  "changed_keys": ["name", "sections"],
  "comments_discarded": 3,
  "backup": "uib_bec_v2.20261111T115010613163Z.yaml"
}
```

| Pole | Popis |
|------|-------|
| `op` | `designer_create_collection`, `designer_update_collection`, `designer_create_template`, `designer_update_template` |
| `via` | vždy `designer` — odliší návrhář od editoru YAML |
| `change` | `created`, `updated`, nebo `unchanged` (soubor se nepřepsal) |
| `changed_keys` | názvy změněných klíčů nejvyšší úrovně (max. 40), nikdy hodnoty |
| `comments_discarded` | počet zahozených řádků komentářů |
| `backup` | název zálohy v `.designer_backup/` |
| `reject_code` | u odmítnutého uložení: `invalid`, `exists`, `stale`, `rewrite_not_confirmed`, `not_found`, `unsupported` |

Kontrolní endpointy (`…/check`, `…/check-template`) nic nemění a při úspěchu se neauditují; odmítnutý pokus bez oprávnění ano. Smazání šablony z návrháře jde přes stávající `DELETE /api/v1/templates/…` (`op: delete_template`).

---

## Reference – atributy v návrháři

Atributy, pro které má návrhář ovládací prvek. Ostatní klíče se zobrazí v bloku *Other attributes* a zůstanou beze změny.

| Objekt | Atributy |
|--------|----------|
| šablona | `template_id`, `name`, `version`, `status`, `category`, `description`, `abstract`, `extends`, `meta` |
| sekce | `id`, `title`, `description`, `hint`; v `section_group` navíc `note`, `always_expanded` |
| sekce `table` | `allow_append_row`, `allow_delete_row`, `hints`, `append_row_template`, `rows` |
| pole | `key`, `label`, `type`, `options`, `auto` / `auto_value`, `editable`, `required`, `placeholder`, `example`, `value`, `hint`, `visible_if`, `required_if` |
| sloupec | `key`, `label`, `type`, `options`, `editable` |
| skupina kroků | `title`, `id`, `note`, `hints` |
| krok | `action`, `hint`, `example`, `id` |

Typ sekce se volí při vložení z palety a dál se nemění. Seznam typů sekcí, polí, barev stavů a tokenů formátu ID vrací `GET /api/v1/admin/designer/catalog` — paleta se staví z něj.

---

## Speciální témata

### Bezpečnost

- **Přístup:** stránky chrání `require_web_admin` (jiná role je přesměrována na `/dashboard`), API `require_admin` (`403`). Role kolekce (`collection_admin`) k návrháři nestačí.
- **Validace:** rozhoduje server; kontroly v prohlížeči jsou jen pohodlí.
- **Cesty:** ID kolekce a název souboru šablony musí být slug `[a-z0-9_-]`, `template_id` jen `[A-Za-z0-9_-]`. Neznámá kolekce vrací `404` dřív, než se sáhne na adresář šablon.
- **XSS:** stránka skládá DOM přes `textContent` a vlastnosti prvků, uživatelská data se nikdy nespojují do HTML. Náhled kreslí `UniForms.render`, který HTML sanitizuje. Hodnoty ze serveru se do skriptu dostávají jen přes `|tojson`.
- **CSRF:** zápisy vyžadují `Content-Type: application/json` jako zbytek API.

### Použití bez webové vrstvy

Převod model ↔ YAML, validace i bezpečný zápis jsou ve službě `uniforms/services/designer_service.py`, která nezávisí na FastAPI. Lze ji volat ze skriptu:

```python
import asyncio
from pathlib import Path
from uniforms.services import designer_service as ds

collections = Path("data/collections")
loaded = ds.load_collection(collections, "zoo")
model = loaded["model"]
model["workflow"]["states"].append({"id": "archived", "label": "Archiv", "color": "dark"})

result = ds.save_collection(
    collections, "zoo", model,
    base_hash=loaded["source"]["hash"],
    confirm_rewrite=True,          # soubor má komentáře – přepis výslovně potvrzuji
)
print(result["change"], result["backup"])

# šablony: funkce jsou async (stejně jako TemplateService)
tpl_dir = Path("data/schemas/zoo")
tpl = asyncio.run(ds.load_template(tpl_dir, "zoo-pstros-v1"))
print(ds.check_template(tpl_dir, tpl["model"])["issues"])
```

V režimu `create_app(include_web=False)` zůstává API návrháře dostupné; chybí jen HTML stránky.

### Omezení

- Komentáře uvnitř souboru (mimo úvodní blok) a původní formátování se při přepisu ztrácejí — návrhář se předem zeptá a uloží zálohu.
- Čísla zapsaná jako `1.0` se po průchodu prohlížečem uloží jako `1`.
- Typ existující sekce nelze změnit; vlastní typy sekcí, starší zápis sloupců tabulky (seznam řetězců), blok `result` checklistu, `workflow` šablony a `option_hints` se zachovávají, ale upravují se jen v editoru YAML.
- Šablony se ukládají jednotlivě; rozpracované změny žijí jen v otevřené stránce.
- Smazání a přejmenování kolekce zůstává na stránce Admin → Collections.

---

## Přehled API / funkcí

### REST API – `/api/v1/admin/designer` (vše `system_admin`)

| Metoda | Endpoint | Popis |
|--------|----------|-------|
| `GET` | `/catalog` | Paleta: typy sekcí a polí, barvy, tokeny, výchozí modely |
| `GET` | `/collections` | Přehled kolekcí s počtem šablon |
| `GET` | `/collections/{id}` | Model kolekce, `source`, šablony, klíče polí |
| `POST` | `/collections` | Vytvoření kolekce z modelu |
| `PUT` | `/collections/{id}` | Uložení modelu kolekce |
| `POST` | `/collections/{id}/check` | Kontrola modelu kolekce — nic nezapisuje |
| `GET` | `/collections/{id}/templates/{template_id}` | Model šablony, `source`, zděděné sekce |
| `POST` | `/collections/{id}/templates` | Vytvoření šablony z modelu |
| `PUT` | `/collections/{id}/templates/{template_id}` | Uložení modelu šablony |
| `POST` | `/collections/{id}/check-template` | Kontrola, náhled a YAML šablony — nic nezapisuje |

Podrobnosti a příklady: [API.md](API.md#admin--collection-designer--apiv1admindesigner).

### `designer_service`

| Funkce | Popis |
|--------|-------|
| `catalog(terminology_defaults)` | Katalog pro paletu a atributy |
| `load_collection(dir, id)` / `load_template(dir, template_id)` | Načte model a popis zdroje |
| `check_collection(model, id)` / `check_template(dir, model)` | Kontrola bez zápisu (nálezy, YAML, náhled) |
| `save_collection(dir, id, model, …)` / `save_template(dir, model, …)` | Validace a bezpečný zápis |
| `lint_collection(model)` / `lint_template(model, dir)` | Jen nálezy návrháře |
| `dump_yaml(model, header)` | Model → kanonický YAML (ověřuje zpětné načtení) |
| `analyze_source(content, data)` | Hash, komentáře, kotvy, kanoničnost souboru |
| `list_templates(dir)` / `collection_field_keys(dir)` | Přehled šablon včetně abstraktních, klíče polí |

### Soubory

| Soubor | Role |
|--------|------|
| `uniforms/services/designer_service.py` | model ↔ YAML, lint, zápis, zálohy |
| `uniforms/api/v1/designer.py` | tenké HTTP routy, auditní identifikátory |
| `uniforms/static/js/designer_model.js` | operace nad modelem bez DOM |
| `uniforms/static/js/designer.js` | průvodce, plátno, drag & drop, panel atributů |
| `uniforms/templates/admin_designer.html`, `admin_designer_editor.html` | stránky |
| `scripts/check_designer_roundtrip.py` | ověření, že přepis nezmění existující definice |
| `scripts/test_designer_model.js` | testy operací nad modelem (`node scripts/test_designer_model.js`) |
