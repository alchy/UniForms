# HANDOVER — stav a zbytek práce

Rozcestník pro další session. **Není to dokumentace** — ta je v [`docs/`](docs/) a v
[`README.md`](README.md) a je zdrojem pravdy o tom, jak aplikace funguje. Tady je jen to, co
v dokumentaci být nemá: stav nasazení, otevřená rozhodnutí, co zbývá a zvláštnosti tohohle stroje.

> **Všude jen současný stav.** Soubor se přepisuje, ne dopisuje; historie je v gitu.
> **Před prací ověř tvrzení o stavu proti kódu, službě a logu** — handover zastará první.

Jazyk: identifikátory v kódu anglicky, komentáře česky (v Pythonu často bez diakritiky),
dokumentace česky s diakritikou podle [`docs/HOW2WRITE.md`](docs/HOW2WRITE.md). UI texty anglicky.

---

## Stav k 12. 11. 2026 (odpoledne)

**Nasazeno.** `uniforms.service` restartovaná 12. 11. 2026 15:08 CET, běží s kódem z `main`
(knihovny bloků, pole `type: user`, časy v UTC). Start bez chyb, `/login` vrací 200.
V prohlížeči ručně ověřeno nebylo.

`main` je pushnutý do `origin/main`. Větve `feat/block-libraries-user-time-fields` a `fix/quick-wins`
jsou v `main` celé, dají se smazat.

V pracovním stromu zůstává jen nesledované `data/schemas/evidence-zlatych-cihel/` (viz Otevřená rozhodnutí).

### Po nasazení

- Uživatelé, kteří upravují záznamy: **tvrdé obnovení (Ctrl+F5)**. Server u statických
  souborů neposílá `Cache-Control`; starý `uniforms.js` z cache by posílal `datetime` bez
  pásma a server by uložení odmítl `422`.
- Ověřit v prohlížeči: přihlášení, `/templates/zoo`, detail záznamu (pole Ošetřovatel = výběr
  uživatele), Settings → Date & time (uložit), Designer → Templates (záložky Forms / Building blocks).

### Co je nového (12. 11. 2026)

| oblast | dokumentace |
|---|---|
| knihovny bloků: `extends` + `override` / `remove` / `use`, Designer záložky a karty bloků | [SABLONY.md §10](docs/SABLONY.md#10-knihovny-bloků-a-dědičnost), [COLLECTION_DESIGNER.md](docs/COLLECTION_DESIGNER.md#formuláře-a-knihovny-bloků) |
| pole `type: user` + `GET /collections/{id}/members` | [SABLONY.md](docs/SABLONY.md#user--uživatel-kolekce), [API.md](docs/API.md#get-apiv1collectionsidmembers) |
| okamžiky v UTC, typy `date` / `time`, Settings → Date & time | [CAS.md](docs/CAS.md) |

### Jak bylo ověřeno

V repu **nejsou testy backendu** (jen `scripts/test_designer_model.js`, 12 testů, zelené).
Ověřovalo se ad-hoc skripty mimo repo:

- skutečná aplikace na portu 18950 s kopií `data/` a čistou DB (smoke testy přes HTTP),
- Designer v jsdom proti této instanci,
- resolver: všech 10 šablon dává totožný výstup jako původní prepend resolver,
- všech 50 existujících záznamů jde uložit beze změny (žádné falešné `422`).

---

## Zbývá

1. **Ověření v prohlížeči** – viz Po nasazení.
2. **Patička s pásmem v auditu** (`admin_audit.html`): časy se tam dnes zobrazují v pásmu
   prohlížeče (`toLocaleString`). Má být pásmo ze Settings + jedna věta v patičce
   („Times shown in Europe/Prague (UTC+01:00)"). Totéž `admin_users.html` (`created_at`).
3. **Seznam záznamů**: když `list_columns` obsahuje časové pole (`last_saved`), ukáže se
   surové ISO. Formátovat přes `UniForms.time.formatTyped`.
4. **Designer – „New block from selected section…"**: přesun sekce formuláře do knihovny
   (zbytek fáze 6 návrhu). Dnes se blok přidá jen v knihovně samotné.
5. **Testy backendu**: resolver (`override`/`remove`/`use`, cykly), `invalid_typed_values`,
   `changed_user_values`, settings API. Ad-hoc skripty z této práce se ztratily se scratchpadem.
6. **Migrace starých hodnot bez pásma** (volitelné): dnes se čtou v pásmu z `.env`
   (`TIMEZONE`, výchozí `Europe/Prague`) a přepíšou se na UTC až při změně.

## Otevřená rozhodnutí


- **`data/schemas/evidence-zlatych-cihel/`** – v gitu nesledované, chybí k němu
  `data/collections/evidence-zlatych-cihel.yaml`, takže v aplikaci není vidět. `record_owner`
  v něm je převedený na `type: user` jen na disku. Smazat, nebo doplnit kolekci a commitnout?
- **Výběr data/času**: nativní prvek prohlížeče ukazuje formát podle jazyka prohlížeče, ne podle
  Settings. Jednotný formát i ve výběru by chtěl knihovnu (např. flatpickr) – nerozhodnuto.
- **Stejné `id` vlastní sekce jako blok knihovny** blok **nenahradí**, přidá druhou sekci
  (zpětná kompatibilita). Nahrazuje jen explicitní `override:`. Designer na kolizi upozorní.

## Zvláštnosti stroje

- Služba `uniforms.service`: uživatel `uniforms`, `WorkingDirectory=/www/uniforms`,
  `uvicorn … --port 8084` za reverzní proxy, **bez `--reload`**.
- Repo vlastní `uniforms:uniforms`. Při práci jako root git hlásí „dubious ownership" –
  použít `git -c safe.directory=/www/uniforms …` jen pro daný příkaz, nebo pracovat přes
  `sudo -u uniforms`. **Po práci jako root vrátit vlastnictví**:
  `find /www/uniforms -user root -exec chown -h uniforms:uniforms {} +`
  (jinak root-owned objekty v `.git` a `sed -i` přepsané soubory rozbijí git pro `uniforms`).
- **Push na GitHub** jde jen klíčem uživatele `tech` (účet `alchy`). `origin` je HTTPS bez
  přihlašovacích údajů (fetch funguje, push ne) a `tech` nemá přístup do `/www/uniforms`, proto
  jako root:
  `GIT_SSH_COMMAND="ssh -i /home/tech/.ssh/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/home/tech/.ssh/known_hosts" git -c safe.directory=/www/uniforms push git@github.com:alchy/UniForms.git main:main`,
  pak vrátit vlastnictví a `sudo -u uniforms git fetch origin` (aktualizuje `origin/main`).
- Git nemá nastavenou identitu; commity jsou „Jindrich Nemec", předávat přes `-c user.name=… -c user.email=…`.
- Shell má `cp` jako alias `cp -i` – v neinteraktivních skriptech `\cp -f`.
- `pkill -f <vzor>` zabije i vlastní shell, když vzor obsahuje jeho příkazová řádka – použít `[x]` trik (`bridge_s[e]rver`).
- Nastavení v DB (`data/uniforms.db`, tabulka `settings`): cesty relativní (`data/records` …),
  `designer_enabled = true`, access-manager přes `am.*` (klíč aplikace je v DB – nevypisovat).
- Přihlašování: `AUTH_PROVIDER` z `.env`; pro testovací instanci stačí `AUTH_PROVIDER=simple`
  + vlastní `ADMIN_*` a čistá DB v kopii `data/`.
