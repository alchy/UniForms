# Přihlášení přes access-manager (OTP)

UniForms umí místo lokálního hesla ověřit uživatele **jednorázovým kódem (TOTP)**
přes službu [access-manager](https://github.com/alchy/access-manager). Access-manager
říká *kdo jsi* a *do jakých skupin patříš*; UniForms si z toho odvodí roli a dál
drží vlastní relaci (JWT cookie), vlastní role v kolekcích i vlastní audit.

Dokument je pro **správce instalace UniForms**: jak aplikaci napojit, jak se z
realmových skupin stávají role a co dělat, když přihlášení nefunguje.

Předpoklady: běžící access-manager s realmem, v němž existují uživatelé se
spárovaným TOTP, a přístup do jeho konzole (realm → Applications). UniForms
v access-manageru **nic nezakládá ani nemění** – jen se ho ptá.

---

## Co to je a k čemu slouží?

Organizace, která už access-manager provozuje (např. pro SOC portál), nechce pro
každou aplikaci zakládat další hesla. S napojením platí:

- člověk se přihlásí **svým jménem a kódem z autentikátoru** – stejným, jaký používá
  v ostatních aplikacích téhož realmu;
- **kdo má přístup a v jaké roli**, se spravuje na jednom místě – skupinami v realmu;
- lokální účty s heslem (typicky nouzový správce `admin` / `demo`) fungují dál, pokud
  to nevypnete.

Access-manager je **autentizační** autorita (ověří kód) a pro realmové uživatele
i **autorizační** (skupiny → role). UniForms je autorizační autorita pro lokální
účty a pro role v kolekcích.

---

## Jak to funguje?

```
Přihlašovací formulář UniForms (jméno + kód)
    │
    ▼
SimpleAuthProvider: má účet auth_source=access_manager / není lokálně / režim „všichni přes AM“?
    │ ano                                         │ ne
    ▼                                             ▼
Access.authenticate(jméno, {"totp": kód},      bcrypt ověření lokálního hesla
    purpose="login", client_origin=IP)            │
    │                                             ▼
    ▼                                          role z lokální DB
verdikt ok? ──ne──► 401 (důvod jen do auditu)
    │ ano
    ▼
skupiny v principals:
    uniforms-admin → system_admin
    uniforms-user  → system_reader
    žádná          → 401 (not_in_access_group)
    │
    ▼
lokální řádek users: založit při prvním přihlášení / propsat roli
    │
    ▼
JWT cookie (relace UniForms) – role se při každém požadavku čte z lokální DB
```

Access-manager **nevydává relaci, jen verdikt**. Restart access-manageru proto
nikoho z UniForms neodhlásí a role se do UniForms propíše **při dalším přihlášení**.

---

## Rychlý start

1. V konzoli access-manageru, v realmu, kde jsou vaši uživatelé:
   - založte skupiny **`uniforms-user`** (přístup) a **`uniforms-admin`** (správci)
     a přidejte do nich lidi;
   - v **Applications** zaregistrujte aplikaci `uniforms` a jako povolený rozsah
     zadejte adresu serveru UniForms, *jak ji uvidí access-manager* (viz
     [Povolené adresy klíče](#povolené-adresy-klíče-origin));
   - zkopírujte vydaný klíč (`am_k…_…`) – ukáže se **jen jednou**.
2. Na serveru UniForms nainstalujte klienta:

   ```bash
   .venv/bin/pip install -r requirements-access-manager.txt
   sudo systemctl restart uniforms
   ```

3. V UniForms jako system_admin: **Settings → Remote authentication – access-manager**:
   - *Server URL* `https://access-manager.example.com`
   - *Realm* `uniforms.example.com`
   - *Application key* – vložte klíč z kroku 1
   - **Test connection** → „Connected to realm …: N users, groups OK.“ → **Save**
4. Odhlaste se a přihlaste jménem z realmu a kódem z autentikátoru.
5. **Admin → Users** – v sekci *Access-manager* vidíte všechny uživatele realmu
   a jejich efektivní přístup do UniForms.

---

## Krok za krokem

### 1. Skupiny v realmu

Skupiny jsou jediný zdroj rolí realmových uživatelů. Konvence pro všechny aplikace
napojené na tentýž access-manager je **`<aplikace>-user`** a **`<aplikace>-admin`**
(SOC portál: `soc-user`, `soc-admin`; UniForms: `uniforms-user`, `uniforms-admin`).

| Skupina | Role v UniForms |
|---------|-----------------|
| `uniforms-admin` | `system_admin` – správa uživatelů, kolekcí, šablon, nastavení, audit |
| `uniforms-user` | `system_reader` – přístup ke kolekcím podle rolí v kolekcích |
| žádná z nich | **bez přístupu** – i se správným kódem |

Kdo je v obou, je správce. Názvy jdou změnit v Settings (*Admin group*, *User group*).

Nově zavedený uživatel se může přihlásit rovnou kódem z naskenovaného párovacího QR –
první platný kód párování dokončí. Vyprší-li QR dřív (výchozí 14 dní), přihlášení
končí `expired` a správce realmu musí vydat nové párování.

> **Pozor na záměnu:** skupina `uniforms-admin` dělá ze člověka správce **UniForms**.
> **Správce realmu** access-manageru je jiná identita s jiným tajemstvím a přihlašuje
> se do konzole access-manageru dvěma kódy – do UniForms se s ní nepřihlásíte.

### 2. Aplikace a klíč v access-manageru

Klíč patří jedné aplikaci v jednom realmu a access-manager ho přijme jen z povolených
adres. Přepínač **detail** u aplikace v konzoli rozhoduje, zda UniForms dostane
podrobný důvod odmítnutí (`bad_code`, `replay`, `unknown_user` …). UniForms ho
**nikdy neukáže na formuláři**, jen zapíše do svého auditu – zapnutí usnadní
diagnostiku, vypnutí skryje postranní kanál i před auditem UniForms.

### 3. Konfigurace v UniForms

Settings → *Remote authentication – access-manager*. Hodnoty uložené zde mají
**přednost před `.env`**; prázdné pole znamená „platí `.env` (nebo výchozí)“.
U každého pole je štítek *set here* / *.env* / *default*.

**Aplikační klíč je jen pro zápis.** Po uložení ho stránka ani API nikdy nevrátí –
ukáže jen „Key `k6` is set here“ (nebo „set in `.env`“). Nový klíč starý přepíše;
*Remove key saved here* vrátí platnost klíči z `.env`.

**Test connection** ověří (i pro neuložené hodnoty): dosažitelnost serveru, verzi API,
že klíč patří zadanému realmu, `ready()` realmu a existenci obou skupin.

### 4. Režim přihlášení

| Režim (*Sign-in mode*) | Lokální účty s heslem | Účty označené OTP | Jméno, které lokálně neexistuje |
|------------------------|-----------------------|-------------------|---------------------------------|
| **Local passwords + access-manager** (`simple`, výchozí) | heslem | přes access-manager | přes access-manager; člen skupiny dostane účet |
| **Everyone through access-manager** (`access_manager`) | **přes access-manager** (heslo se nepoužije) | přes access-manager | přes access-manager; člen skupiny dostane účet |

Druhý režim nejde uložit správcem přihlášeným lokálním heslem – zamkl by se.
Nejdřív se přihlaste jako člen `uniforms-admin` přes OTP.

### 5. Přehled přístupu

**Admin → Users** má dvě části:

- **Local accounts** – účty s heslem, role nastavená v UniForms;
- **Access-manager** – všichni uživatelé realmu se skupinami, efektivní rolí
  a důvodem, proč případně přístup nemají.

U realmového uživatele, který se ještě nepřihlásil, lze tlačítkem **předpřipravit**
lokální účet – např. abyste mu přidělili role v kolekcích dřív, než se poprvé přihlásí.
Tužkou se otevře lokální nastavení: zablokování (Inactive) a role v kolekcích.

---

## Přehled konceptů

### Zdroj ověření účtu (`auth_source`)

Každý lokální řádek v tabulce `users` má `auth_source`: `local` (bcrypt heslo)
nebo `access_manager` (OTP). Realmový uživatel dostane řádek s `access_manager`
automaticky při prvním přihlášení; v **Admin → Users → New user** lze OTP účet
založit i ručně (*Sign-in: OTP (access-manager)*, bez hesla).

```bash
# OTP účet založený ručně (heslo se neuvádí – do DB se uloží náhodné, nepoužitelné)
curl -b cookies.txt -X POST https://uniforms.example.com/api/v1/users/ \
  -H "Content-Type: application/json" \
  -d '{"username": "hana", "role": "system_reader", "auth_source": "access_manager"}'
```

### Role ze skupin a lokální řádek

Při každém úspěšném OTP přihlášení se role spočítá ze skupin a **zapíše do lokálního
řádku**. Každý požadavek pak ověřuje roli a `is_active` v lokální DB – deaktivace
v Admin → Users platí okamžitě.

Změna skupin v access-manageru se projeví **až při dalším přihlášení**. Přehled
v Admin → Users ji ukazuje hned („stored … – updates at next sign-in“). Potřebujete-li
přístup odebrat okamžitě, účet v UniForms zablokujte.

### Povolené adresy klíče (`origin`)

Access-manager měří adresu, **ze které přišel požadavek aplikace** (za svou proxy),
a klíč přijme jen z povolených rozsahů. Pro UniForms je to adresa serveru UniForms
tak, jak ji vidí access-manager – běží-li obojí na jednom stroji a UniForms volá
veřejné `https://` jméno, je to **veřejná adresa serveru** (IPv4 i IPv6), ne `127.0.0.1`.

Adresu **člověka** u formuláře posílá UniForms zvlášť jako `client_origin` – jde do
auditu access-manageru a je klíčem omezování pokusů (neúspěchy z jedné adresy brzdí
tu adresu). O přístupu nerozhoduje, protože ji jde podvrhnout.

### Jméno lokálního účtu vs. realmová identita

Má-li lokální účet s heslem stejné jméno jako uživatel realmu, v režimu `simple`
vyhrává lokální účet (heslo) a přehled to označí „name taken by a local password
account“. Přejmenujte nebo smažte lokální účet, má-li se člověk hlásit přes OTP.

---

## Reference – konfigurace

V GUI (Settings) i v `.env`; GUI má přednost.

| Klíč v `.env` | Pole v Settings | Výchozí | Popis |
|---------------|-----------------|---------|-------|
| `ACCESS_MANAGER_URL` | Server URL | – | `https://…` služby; plain `http` jen na loopback |
| `ACCESS_MANAGER_KEY` | Application key | – | klíč aplikace z konzole access-manageru (jen pro zápis) |
| `ACCESS_MANAGER_REALM` | Realm | – | tvrzení: nesoulad s realmem klíče je hlasitá chyba |
| `ACCESS_MANAGER_ADMIN_GROUP` | Admin group | `uniforms-admin` | členové → `system_admin` |
| `ACCESS_MANAGER_USER_GROUP` | User group | `uniforms-user` | členové → `system_reader` |
| `AUTH_PROVIDER` | Sign-in mode | `simple` | `simple` \| `access_manager` (viz Režim přihlášení) |
| `ACCESS_MANAGER_CA` | Custom CA bundle | – | vlastní CA pro certifikát služby; ověření nejde vypnout |
| `ACCESS_MANAGER_HOME` | – (jen `.env`) | – | lokální režim bez služby: datový adresář access-manageru na tomtéž stroji (+ `ACCESS_MANAGER_REALM`) |

GUI hodnoty jsou v SQLite (`settings`, klíče `am.*`); `uniforms.db` má práva `0600`.
Obecné `GET /api/v1/settings/` ani stránka Settings klíče `am.*` nevydávají.

---

## Řešení problémů

Každý pokus o přihlášení je v **Admin → Audit** (`op: login`). Podrobnosti:

| Audit | Význam | Co s tím |
|-------|--------|----------|
| `am_outcome: denied`, `am_reason: bad_code` | špatný kód | hodiny telefonu, správná položka v autentikátoru (`<realm>-member-<jméno>`) |
| `am_reason: replay` | kód z tohoto 30s okna už byl použit | počkat na další kód |
| `am_reason: unknown_user` | jméno v realmu není | překlep, nebo jiný realm |
| `am_reason: disabled` | uživatel je v realmu zakázaný | povolit v konzoli access-manageru |
| `am_reason: expired` | párovací QR vypršel dřív, než ho člověk použil | v konzoli access-manageru vydat nové párování |
| `am_reason: no_secret` | nedokončené zavedení uživatele (adresář bez tajemství) | v konzoli access-manageru uživatele spárovat |
| `am_outcome: need_factor` | kód nebyl zadán | zadat kód |
| `am_outcome: throttled` | příliš mnoho pokusů | formulář ukáže, za kolik sekund to jde znovu (HTTP 429) |
| `reason: not_in_access_group` | kód platný, ale člověk není v `uniforms-user` / `uniforms-admin` | přidat do skupiny |
| `reason: inactive` | lokální účet je zablokovaný | Admin → Users → odblokovat |
| `am_outcome: unavailable` | služba nedostupná / špatně nastavená | Settings → **Test connection**; log `journalctl -u uniforms` |
| `am_reason` chybí u `denied` | aplikace nemá v access-manageru zapnutý *detail* | záměr; pro diagnostiku lze zapnout |

Další časté chyby **Test connection**:

| Hláška | Příčina |
|--------|---------|
| `realm nesouhlasi: ocekavano …, sluzba hlasi …` | klíč patří jinému realmu, než je zadán |
| `… groups do not exist there: …` | skupina v realmu chybí nebo je v Settings překlep |
| HTTP 401/403 od služby | neplatný / odvolaný klíč, nebo požadavek z adresy mimo povolené rozsahy |
| `access-manager client is not installed` | chybí `pip install -r requirements-access-manager.txt` |

---

## Přehled API

| Endpoint | Role | Popis |
|----------|------|-------|
| `GET /api/v1/admin/access-manager/` | system_admin | efektivní konfigurace, zdroj hodnot, stav klíče (bez klíče) |
| `PUT /api/v1/admin/access-manager/` | system_admin | uložení; vynechané pole beze změny, `""` = zpět na `.env` |
| `POST /api/v1/admin/access-manager/test` | system_admin | test připojení (i pro neuložené hodnoty) |
| `GET /api/v1/admin/access/` | system_admin | efektivní přístup: lokální účty + uživatelé realmu |

Podrobnosti v [API.md](API.md#admin--access-manager--apiv1adminaccess-manager).

| Modul | Účel |
|-------|------|
| `uniforms/auth/access_manager_auth.py` | klient, efektivní konfigurace (GUI › `.env`), ověření kódu, adresář realmu |
| `uniforms/auth/simple_auth.py` | volba heslo / OTP, mapování skupin na role, zakládání účtů |
| `uniforms/api/v1/access_manager_config.py` | API nastavení a testu |
| `uniforms/api/v1/access_overview.py` | přehled přístupu |
