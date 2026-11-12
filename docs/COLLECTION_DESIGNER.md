# Collection Designer

Collection Designer je webový návrhář, ve kterém `system_admin` vytváří a upravuje kolekce a jejich šablony formulářů myší a vyplňováním atributů — bez psaní YAML. Dokument je určen administrátorům, kteří s návrhářem pracují, a vývojářům, kteří chtějí stejné funkce volat z vlastního kódu nebo přes API.

YAML soubory zůstávají jedinou definicí (`data/collections/<id>.yaml`, `data/schemas/<kolekce>/*.yaml`). Návrhář je čte a zapisuje; nic dalšího si neukládá. Formát souborů popisují [KOLEKCE.md](KOLEKCE.md) a [SABLONY.md](SABLONY.md).

---

## Co to je a k čemu slouží?

Dosud se kolekce a šablony upravovaly v editoru surového YAML (Admin → Collections, Templates → Edit). To vyžaduje znát klíče, odsazení a pravidla formátu. Collection Designer nabízí totéž jako formulář:

- **průvodce kolekcí** v šesti krocích — základ, stavy workflow, záznamy (formát ID, sloupce seznamu, titulek, převzetí), role a terminologie, šablony, kontrola a uložení,
- **návrhář šablony** — paleta objektů (sekce, pole, sloupce, kroky, sdílené bloky), plátno formuláře s přetahováním, panel atributů vybraného objektu, živý náhled a zobrazení výsledného YAML,
- **knihovny bloků** — sekce sdílené více formuláři; na plátně je u každého bloku vidět, odkud pochází, a jedním klikem se dá upravit v knihovně, jen pro jeden formulář, vynechat nebo nahradit jiným blokem.

Editory surového YAML zůstávají a návrhář na ně odkazuje. Hodí se pro věci, které návrhář neumí (viz [Omezení](#omezení)), a pro soubory s komentáři, o které nechceš přijít.

Stránka je v menu **Admin → Collection Designer** (`/admin/designer`) a vidí ji jen `system_admin`. Ostatní přístupová práva se nemění.

> **Zapnutí:** návrhář je ve výchozím stavu **vypnutý**. Zapíná se v **Settings → Features → Enable Collection Designer**
> (nastavení `designer_enabled`, uložené v DB). Dokud je vypnutý, jeho stránky `/admin/designer*` i celé API
> `/api/v1/designer/*` odpovídají `404` (jako by neexistovaly), položka v menu i odkazy na stránkách Collections
> a Templates jsou skryté a kolekce a šablony se upravují v editorech YAML. Přepnutí platí okamžitě (bez restartu)
> a zapíše se do [auditu](AUDIT.md) (`op: update_settings`, `changed: ["designer_enabled"]`).

---

## Jak to funguje?

Návrhář nepracuje s textem YAML, ale s **modelem** — slovníkem, který vznikne načtením YAML souboru. Model se **nenormalizuje**: zkratky (`auto:`, `example:`, plochý `steps:`) i klíče, pro které návrhář nemá ovládací prvek, v něm zůstávají tak, jak jsou v souboru. Díky tomu se při uložení neztratí nic, co návrhář nezná.

```
data/schemas/zoo/zoo_pstros_v1.yaml
    │
    ▼  designer_service.load_template()        yaml.safe_load, bez normalizace
model (dict)  +  source {hash, comments, …}
    │
    ▼  GET /api/v1/designer/collections/zoo/templates/zoo-pstros-v1
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
5. Otevře se krok *Templates* na záložce **Forms**. Klikni **New form**, vyplň název a potvrď **Start designing**.
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
| Templates | záložky **Forms** (šablony pro záznamy) a **Building blocks** (knihovny bloků), otevření návrháře | soubory v `data/schemas/<id>/` |
| Review & save | kontrola serverem, výsledný YAML, uložení | — |

Změny v krocích se drží jen v prohlížeči, dokud je v posledním kroku neuložíš. Krok *Templates* je u nové kolekce zamčený, dokud kolekce neexistuje — šablony se ukládají do jejího adresáře.

ID kolekce nelze po vytvoření změnit: je to název souboru a klíč, podle kterého se párují role uživatelů.

> **Poznámka:** Řádky stavů a sloupců lze přeřadit tažením za úchyt vlevo nebo šipkami. U klíčů sloupců, titulku a pole pro převzetí návrhář napovídá klíče polí nalezené v šablonách kolekce a upozorní, když klíč v žádné šabloně není.

### Návrhář šablony

Obrazovka má tři části:

| Část | K čemu slouží |
|------|---------------|
| Paleta (vlevo) | Objekty k vložení: sekce, **Building blocks (shared)** (bloky knihoven), pole, **System (app-defined)** (automatická hodnota, User, Record owner), sloupce tabulky (i datum/čas), skupiny a kroky checklistu. |
| Plátno (uprostřed) | Struktura šablony. Nahoře karta šablony, pod ní bloky knihovny (každý jako samostatná fialová karta) a vlastní sekce formuláře. |
| Atributy (vpravo) | Vlastnosti vybraného objektu a akce: posun nahoru/dolů, duplikace, smazání. |

Objekt vložíš **přetažením** z palety na plátno, nebo **kliknutím** — vloží se k právě vybranému objektu. Existující objekty lze přetahovat v rámci sekce i mezi sekcemi. Plátno dovolí jen smysluplné umístění:

| Objekt | Kam ho lze umístit |
|--------|--------------------|
| sekce `header`, `section_group` | jen na nejvyšší úroveň |
| sdílený blok (Building blocks) | jen na nejvyšší úroveň |
| sekce `form`, `table`, `checklist` | na nejvyšší úroveň nebo do `section_group` |
| pole | do sekce `header` nebo `form` |
| sloupec | do sekce `table` |
| skupina kroků | do sekce `checklist` |
| krok | do checklistu bez skupin, nebo do skupiny kroků |

Pod plátnem běží průběžná kontrola serverem (chyby a varování s cestou k objektu). Přepínač **Live preview below** zobrazí pod návrhem náhled, který se obnovuje při každé změně; záložka **Preview** ukáže náhled přes celou šířku a **YAML** výsledný soubor. Náhled kreslí stejný renderer jako detail záznamu (`UniForms.render`), včetně bloků knihoven – s vynechanými, upravenými i vloženými bloky přesně tak, jak je dostane nový záznam.

Tlačítko **Undo** vrací poslední změny (až 60 kroků). Šablona se zapíše až tlačítkem **Save template**.

> **Pozor:** `template_id` nelze po prvním uložení změnit. Pro jiné ID vytvoř novou šablonu.

### Formuláře a knihovny bloků

Krok *Templates* má dvě záložky – to je první volba, co chceš upravovat:

| Záložka | Obsahuje | Tlačítko |
|---------|----------|----------|
| **Forms** | šablony, ze kterých vznikají záznamy; u každé „LIBRARY · <knihovna>" a počet sekcí | **New form** |
| **Building blocks** | knihovny bloků (`abstract: true`); jejich bloky jako štítky a „Used by" | **New block library** |

Ve formuláři, který používá knihovnu (*Uses library*, v YAML `extends`), je každý blok knihovny
samostatná fialová karta se zámkem, štítkem knihovny a přehledem polí. Kliknutí na kartu nabídne:

| Volba | Co udělá | V YAML |
|-------|----------|--------|
| **Edit in library** | otevře knihovnu s vybraným blokem; změna platí pro všechny formuláře, které ho používají | — |
| **Customize for this form only** | formulář dostane vlastní kopii bloku (oranžová karta „CUSTOMIZED") | `override: <id>` |
| **Replace with another block…** | na místě bloku použije jiný sdílený blok („REPLACED") | `override: <id>` + `use: <ref>` |
| **Remove from this form** (ikona 👁) | blok se ve formuláři nepoužije; zůstane přeškrtnutý s tlačítkem **Restore** | `remove: <id>` |

Upravená nebo nahrazená karta má tlačítko **Reset to library version**, které vrátí blok z knihovny.

Jednotlivý blok z jiné knihovny vložíš z palety **Building blocks (shared)** (kliknutím nebo
přetažením). Vložený blok je živý odkaz (`use:`): karta „EMBEDDED" ukáže jeho obsah, **Edit in library**
ho otevře v knihovně a **Detach (copy here)** z odkazu udělá vlastní kopii. V atributech lze vložený
blok vyměnit za jiný nebo mu dát jiné `id`.

Při úpravě knihovny (nebo formuláře, ze kterého jiné formuláře berou bloky) je nahoře žlutý pruh se
seznamem dotčených formulářů a tlačítkem **Back to <formulář>**; uložení se ještě potvrdí. Změna
knihovny se projeví jen u **nových** záznamů. Knihovnu nejde uložit, pokud by smazala nebo
přejmenovala blok, který některý formulář upravuje, vynechává nebo vkládá.

Pravidla a YAML: [SABLONY.md – Knihovny bloků a dědičnost](SABLONY.md#10-knihovny-bloků-a-dědičnost).

> **Pozor:** Knihovna musí existovat dřív než formulář, který ji používá – nejdřív ulož knihovnu, potom formulář.

### Pole aplikace a časová pole

Skupina palety **System (app-defined)** obsahuje pole, jejichž hodnoty určuje aplikace, ne šablona:
*Automatic value* (`auto:`), *User* a *Record owner* (`type: user` – výběr z uživatelů kolekce,
atribut *Users from* = `source`). Pole typu User má na plátně odznak „app list".

Časové typy: pole *Date & time* (okamžik, ukládá se v UTC – atribut *Time zone shown* = `display_tz`),
*Date* a *Time of day* (denní čas bez převodu); v tabulkách sloupce *Date column*, *Time column*
a *Date & time column*. Kdy který použít: [CAS.md](CAS.md).

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
  "path": "/api/v1/designer/collections/soc/templates/uib-bec-v2",
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
| šablona | `template_id`, `name`, `version`, `status`, `category`, `description`, `abstract` (*Block library*), `extends` (*Uses library*), `meta` |
| sekce | `id`, `title`, `description`, `hint`; v `section_group` navíc `note`, `always_expanded` |
| blok knihovny (karta) | akce *Customize* (`override`), *Replace…* (`override` + `use`), *Remove* (`remove`), *Restore*, *Reset to library version* |
| vložený blok | `use` (*Block*), `id`; akce *Detach (copy here)* |
| sekce `table` | `allow_append_row`, `allow_delete_row`, `hints`, `append_row_template`, `rows` |
| pole | `key`, `label`, `type`, `options`, `source` (jen `user`), `display_tz` (jen `datetime`), `auto` / `auto_value`, `editable`, `required`, `placeholder`, `example`, `value`, `hint`, `visible_if`, `required_if` |
| sloupec | `key`, `label`, `type` (`text`, `select`, `textarea`, `date`, `time`, `datetime`), `options`, `display_tz`, `editable` |
| skupina kroků | `title`, `id`, `note`, `hints` |
| krok | `action`, `hint`, `example`, `id` |

Typ sekce se volí při vložení z palety a dál se nemění. Seznam typů sekcí, polí, sloupců, zdrojů uživatelů, barev stavů a tokenů formátu ID vrací `GET /api/v1/designer/catalog` — paleta se staví z něj. Bloky knihoven v paletě pocházejí z přehledu šablon (`section_ids`, `section_titles`).

---

## Speciální témata

### Bezpečnost

Návrhář zapisuje soubory, které řídí celou aplikaci, proto má vlastní router (`/api/v1/designer`) s ochranami na jednom místě. Uvažované hrozby a opatření:

| Hrozba | Opatření |
|--------|----------|
| Volání bez oprávnění (jiná role, nepřihlášený, zapomenutá kontrola na nové routě) | `require_admin` je závislost **routeru**, ne jednotlivých rout — platí pro každý endpoint, i později přidaný. Role kolekce (`collection_admin`) nestačí. Stránky chrání `require_web_admin` (přesměrování na `/dashboard`). |
| CSRF z cizí stránky | API je pod `/api/v1` → platí kontrola `Content-Type: application/json`; cookie je `SameSite`. |
| Zápis mimo datový adresář (path traversal) | Klient nikdy neposílá cestu. Posílá jen ID kolekce a název souboru šablony, oba omezené na slug `[a-z0-9_-]` (pydantic `pattern` i kontrola ve službě); `template_id` jen `[A-Za-z0-9_-]`. Neznámá kolekce vrací `404` dřív, než se sáhne na adresář šablon. |
| Podstrčení škodlivého YAML | Klient YAML neposílá vůbec — posílá JSON model a YAML z něj skládá server (`yaml.SafeDumper`). Soubory se čtou výhradně přes `yaml.safe_load`. |
| Nevalidní definice, která rozbije kolekci | Před každým zápisem se výsledný YAML znovu ověří stávajícími validátory (`parse_collection_yaml`, `TemplateService._validate`) a lintem návrháře; při chybě se nezapíše nic. |
| Zahlcení serveru obřím modelem | Tělo požadavku max. 2 MB (`413`); model max. 50 000 hodnot, hloubka 12, 500 položek v seznamu (sekce, pole, options, řádky), 200 klíčů v objektu, 20 000 znaků na text (`422`). Obálky požadavků mají `extra="forbid"`. |
| Dva administrátoři si potichu přepíší změny | `base_hash` (SHA-256 načteného souboru) je u `PUT` povinný; nesedí-li, uložení skončí `409 stale`. |
| Poškozený soubor při pádu uprostřed zápisu | Zápis jde do dočasného souboru a přejmenováním (`os.replace`). Každé uložení se týká jednoho souboru — kolekce a šablony se neukládají společně, takže nevzniká napůl zapsaná sada. |
| Tichá ztráta ručně psaného obsahu | Potvrzení přepisu, záloha v `.designer_backup/`, zachování úvodního komentáře a neznámých klíčů (viz výše). |
| XSS přes názvy, popisky a hodnoty | Stránka skládá DOM přes `textContent` a vlastnosti prvků — uživatelská data se nikdy nespojují do HTML ani do inline `onclick`. Náhled kreslí `UniForms.render`, který HTML sanitizuje. Hodnoty ze serveru jdou do skriptu jen přes `|tojson`. |
| Nedohledatelná změna | Každý zápis i odmítnutý pokus je auditní událost s `collection_id`, `template_id`, `change`, `changed_keys` — bez hodnot a těl požadavků. |

> **Poznámka:** Návrhář nepřidává žádnou novou moc: `system_admin` mohl tytéž soubory přepsat už editorem surového YAML. Šablona nemůže spouštět kód — je to deklarativní popis formuláře a renderer její texty sanitizuje.

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
- Počáteční stav `done` kroku a `hints` u jiných sekcí než `table` nemají ovládací prvek (zobrazí se v *Other attributes*).
- Smazání a přejmenování kolekce zůstává na stránce Admin → Collections.
- Přesun sekce formuláře do knihovny („New block from selected section") zatím není – blok se do knihovny přidá v ní samotné.
- Pořadí bloků knihovny ve formuláři nelze měnit; vlastní a vložené sekce následují za nimi.

---

## Přehled API / funkcí

### REST API – `/api/v1/designer` (vše `system_admin`, vynuceno na routeru)

| Metoda | Endpoint | Popis |
|--------|----------|-------|
| `GET` | `/catalog` | Paleta: typy sekcí a polí, barvy, tokeny, výchozí modely |
| `GET` | `/collections` | Přehled kolekcí s počtem šablon |
| `GET` | `/collections/{id}` | Model kolekce, `source`, šablony, klíče polí |
| `POST` | `/collections` | Vytvoření kolekce z modelu |
| `PUT` | `/collections/{id}` | Uložení modelu kolekce |
| `POST` | `/collections/{id}/check` | Kontrola modelu kolekce — nic nezapisuje |
| `GET` | `/collections/{id}/templates/{template_id}` | Model šablony, `source`, bloky knihovny (`inherited`), vložené bloky (`embedded`) |
| `POST` | `/collections/{id}/templates` | Vytvoření šablony z modelu |
| `PUT` | `/collections/{id}/templates/{template_id}` | Uložení modelu šablony |
| `POST` | `/collections/{id}/check-template` | Kontrola, náhled a YAML šablony, `inherited` a `embedded` — nic nezapisuje |

Podrobnosti a příklady: [API.md](API.md#admin--collection-designer--apiv1designer).

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
| `list_templates(dir)` / `collection_field_keys(dir)` | Přehled šablon včetně knihoven (`section_ids`, `section_titles`, `uses`, `removes`), klíče polí |
| `inherited_sections(dir, parent_id, own_id)` | Bloky knihovny v pořadí: `sections`, `origins`, `indexes`, `ids`, `chain` |
| `embedded_blocks(dir, model)` | Obsah vložených bloků (`use:`) nebo chyba odkazu |

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
