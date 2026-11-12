# Datum, čas a časová pásma

Jak UniForms ukládá a zobrazuje časové údaje: okamžiky v UTC, zobrazení v pásmu z nastavení,
kalendářní dny a denní časy bez převodu. Dokument je pro správce, kteří navrhují šablony
(volba správného typu pole) a nastavují aplikaci (Settings → Date & time).

Předpoklady: znalost formátu šablon ([SABLONY.md](SABLONY.md)).

---

## Co to je a k čemu slouží?

Časový údaj může znamenat tři různé věci a každá se musí ukládat jinak:

- **Okamžik**, který nastal – vylíhnutí, prohlídka u veterináře, uložení záznamu. Je stejný
  pro celý svět, jen se v různých pásmech jinak zapisuje.
- **Kalendářní den** – datum narození. Nemá hodinu ani pásmo.
- **Denní čas** – rozvrh, „krmení v 07:00". Platí v místním čase každý den, v zimě i v létě.

Kdyby se všechno ukládalo jako místní čas bez pásma, změna pásma nebo přechod na letní čas by
údaje tiše posunul. Proto UniForms ukládá okamžiky **v UTC** (stejně jako access-manager)
a pásmo použije až při zobrazení.

---

## Jak to funguje?

```
Analytik vybere 13.10.2026 11:04   (pásmo ze Settings: Europe/Prague, letní čas UTC+02:00)
    │
    ▼
Prohlížeč (uniforms.js): převod místní čas → UTC
    │
    ▼
PATCH /api/v1/records/…   field.value = "2026-10-13T09:04:00Z"
    │   server ověří formát (jinak 422)
    ▼
Uloženo v UTC – nezávisle na pásmu serveru i uživatele
    │
    ▼
Zobrazení: UTC → pásmo ze Settings → "13.10.2026 11:04"  + značka "Europe/Prague (UTC+02:00)"
```

| Typ | Uložená hodnota | Zobrazení | Převod pásma | Značka u pole |
|-----|-----------------|-----------|:------------:|---------------|
| `datetime` | `2026-10-13T09:04:00Z` | `13.10.2026 11:04` | ano | „Time zone: Europe/Prague (UTC+02:00)" |
| `date` | `2026-10-13` | `13.10.2026` | ne | žádná |
| `time` | `07:00` | `07:00` / `7:00 AM` | ne | „Local time – not converted between time zones" |

Změna pásma nebo formátu v Settings mění **jen zobrazení** – uložená data se nikdy nepřepisují.

---

## Rychlý start

Šablona se všemi třemi typy:

```yaml
template_id: cas-ukazka-v1
name: "Ukázka časových polí"
version: '1.0'
status: draft

sections:
  - id: header
    title: Hlavička
    type: header
    fields:
      - { key: record_id, label: "ID záznamu", auto: record_id }
      - { key: last_saved, label: "Poslední uložení", auto: last_saved }

  - id: events
    title: Události
    type: form
    fields:
      - { key: born_at, label: "Datum vylíhnutí", type: datetime }
      - { key: birth_day, label: "Den narození", type: date }
      - { key: feeding_time, label: "Čas krmení", type: time }

  - id: diary
    title: Deník
    type: table
    allow_append_row: true
    columns:
      - { key: when, label: "Kdy", type: datetime }
      - { key: entry, label: "Záznam", type: text }
```

Uložte ji do `data/schemas/<kolekce>/cas_ukazka_v1.yaml` a založte záznam. Výsledek:

- „Poslední uložení" ukazuje čas v pásmu ze Settings se značkou pásma.
- „Datum vylíhnutí" má výběr data a času a pod ním „Time zone: Europe/Prague (UTC+01:00)".
- „Čas krmení" má výběr času a poznámku, že se nepřevádí.
- Sloupec „Kdy" má v hlavičce pásmo, např. „(Europe/Prague (UTC+01:00))".

---

## Krok za krokem

1. **Nastavte pásmo a formát.** Settings → Date & time: pásmo (IANA název, např. `Europe/Prague`),
   formát data a 12/24h. Náhled ukazuje aktuální čas. Uložení platí okamžitě na všech stránkách.
2. **Zvolte typ pole podle významu.** Okamžik → `datetime`, den → `date`, rozvrh → `time`.
   V Collection Designeru jsou typy „Date & time", „Date", „Time of day" a sloupce
   „Date column", „Time column", „Date & time column".
3. **Rozhodněte o zobrazení v UTC.** Pole, které má být vždy v UTC (např. čas z logu jiného
   systému), dostane `display_tz: utc`. Ukládá se stejně – v UTC.
4. **Uložte a ověřte.** Značka pásma pod polem ukazuje, v jakém pásmu analytik čas vidí a zadává.

---

## Přehled konceptů

### Okamžik (`datetime`)

Ukládá se v UTC ve tvaru ISO 8601 s `Z`. Prohlížeč ho zobrazí i zadá v pásmu ze Settings
(nebo v UTC při `display_tz: utc`). Posun pásma se počítá k datu hodnoty, takže stejné pole
ukáže v zimě `UTC+01:00` a v létě `UTC+02:00`.

```yaml
- key: vet_visit
  label: Prohlídka u veterináře
  type: datetime
  display_tz: local
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `type` | ✓ | `datetime` |
| `display_tz` | | `local` = pásmo ze Settings (výchozí) \| `utc` |

### Kalendářní den (`date`)

Den bez času a bez pásma, uložený jako `YYYY-MM-DD`. Zobrazí se ve formátu ze Settings.

```yaml
- key: birth_day
  label: Den narození
  type: date
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `type` | ✓ | `date` |

### Denní čas (`time`)

Čas dne `HH:MM` v místním čase, **bez převodu**. Rozvrh „07:00" musí zůstat 07:00 i po přechodu
na letní čas – převod na UTC by ho posunul o hodinu.

```yaml
- key: feeding_time
  label: Čas krmení
  type: time
```

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `type` | ✓ | `time` |

### Automatické časy (`auto: now`, `auto: last_saved`)

`now` (čas vytvoření) a `last_saved` (čas posledního uložení) vyplní server v UTC. Zobrazí se
jako okamžik – v pásmu ze Settings se značkou pásma.

```yaml
- { key: created_at, label: "Vytvořeno", auto: now }
- { key: last_saved, label: "Poslední uložení", auto: last_saved }
```

| Hodnota `auto` | Uložená hodnota |
|----------------|-----------------|
| `now` | `2026-11-12T09:39:11Z` (při vytvoření) |
| `last_saved` | `2026-11-12T09:39:11Z` (při každém uložení) |

### Nastavení Date & time

Settings → Date & time ukládá tři hodnoty do tabulky `settings` (mění se za běhu, bez restartu).

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `time_zone` | | IANA pásmo zobrazení; výchozí z `.env` (`TIMEZONE`, výchozí `Europe/Prague`) |
| `date_format` | | `DD.MM.YYYY` (výchozí) \| `YYYY-MM-DD` \| `MM/DD/YYYY` \| `DD/MM/YYYY` |
| `time_format` | | `24h` (výchozí) \| `12h` |

```bash
curl -b cookies.txt -X PATCH http://localhost:8080/api/v1/settings/ \
  -H "Content-Type: application/json" -H "X-Requested-With: XMLHttpRequest" \
  -d '{"time_zone": "Europe/Prague", "date_format": "DD.MM.YYYY", "time_format": "24h"}'
```

Neplatné pásmo nebo formát server odmítne (`422`).

### Starší hodnoty bez pásma

Záznamy z doby před ukládáním v UTC mají okamžiky bez pásma (`2026-10-13T11:04`). Čtou se jako čas
**pásma z `.env`** (`TIMEZONE`) – ne pásma ze Settings – takže je pozdější změna Settings neposune.
Při první změně pole se uloží v UTC.

Hodnoty, které nejsou platným datem/časem (např. „ráno" ve sloupci, který byl dřív textový),
zůstanou viditelné jako text s nápovědou formátu. Server je při uložení neodmítne, dokud se nezmění.

> **Poznámka:** Záznam je kopie šablony z okamžiku vzniku. Změna typu pole v šabloně (např. `text`
> → `time`) se projeví jen u **nových** záznamů.

### Kontrola při uložení

Server (`PATCH /api/v1/records/…`) ověří každou **změněnou** hodnotu časových polí a nové hodnoty
v časových sloupcích tabulek. Typ bere z uloženého záznamu, ne z dat poslaných klientem.

| Typ | Musí být | Příklad chyby (`422`) |
|-----|----------|-----------------------|
| `datetime` | ISO 8601 s pásmem (`Z` nebo `±HH:MM`) | `Field 'born_at': expected ISO 8601 in UTC, e.g. 2026-10-13T09:04:00Z` |
| `date` | platné `YYYY-MM-DD` | `Table column 'vet_care.date': expected YYYY-MM-DD, e.g. 2026-10-13` |
| `time` | `HH:MM` nebo `HH:MM:SS`, 00–23 h | `Table column 'feeding.time': expected HH:MM (24h, local time), e.g. 07:00` |

---

## Speciální témata

### Přechod na letní a zimní čas

UTC letní čas nemá – proto je časová osa okamžiků spojitá. Při zadání místního času, který kvůli
přechodu neexistuje (29. 3. 02:30), se čas posune na 03:30. U zdvojené hodiny (25. 10. 02:30)
se použije druhý výskyt, tj. zimní čas.

### Soulad s access-managerem

access-manager zapisuje audit i logy v UTC (`+00:00`). UniForms ukládá okamžiky také v UTC
(`Z` – totéž), takže se časy z obou systémů dají přímo porovnávat.

### Výběr data a času v prohlížeči

Výběr data/času je nativní prvek prohlížeče a během vybírání ukazuje formát podle jazyka prohlížeče.
Formát ze Settings platí všude, kde se hodnota zobrazuje.

> **Pozor:** Po nasazení nové verze proveďte v prohlížeči tvrdé obnovení (Ctrl+F5). Starý
> `uniforms.js` z cache by posílal čas bez pásma a server by uložení odmítl (`422`).

---

## Přehled API / funkcí

| Kde | Co |
|-----|-----|
| `GET` / `PATCH /api/v1/settings/` | `time_zone`, `date_format`, `time_format` |
| `PATCH /api/v1/records/{collection_id}/{record_id}` | kontrola formátu změněných časových hodnot (`422`) |
| `APP_TIME` (globální JS v každé stránce) | `{timezone, date_format, time_format, legacy_timezone}` |
| `UniForms.time` | `parseInstant`, `formatInstant`, `formatDate`, `formatTime`, `formatTyped`, `zoneLabel` – viz [FRONTEND.md](FRONTEND.md) |
| `settings_service.load_time_settings()` / `time_settings()` | načtení / cache nastavení pro šablony stránek |
| `record_service.invalid_typed_values()` | serverová kontrola formátu |
