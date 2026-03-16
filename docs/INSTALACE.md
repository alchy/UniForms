# UniForms – Instalační průvodce

UniForms je webová aplikace pro strukturovaný sběr dat a správu záznamů prostřednictvím YAML šablon. Server je FastAPI + Uvicorn; data jsou lokální (YAML + JSON + SQLite) — žádný cloud, žádná externí databáze.

---

## 1. Požadavky

| Požadavek | Minimální verze | Poznámka |
|-----------|-----------------|---------|
| Python | 3.11 | `python --version` nebo `python3 --version` |
| pip | aktuální | součástí Pythonu |
| Git | libovolná | pro klonování repozitáře |
| Přístup k internetu | — | stažení vendor JS/CSS knihoven |

Aplikace nevyžaduje databázový server, Redis ani žádnou jinou infrastrukturu — vše běží lokálně.

---

## 2. Rychlý start

### Linux / macOS

```bash
# 1. Klonování repozitáře
git clone https://github.com/your-org/UniForms.git
cd UniForms

# 2. Virtuální prostředí a závislosti
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Konfigurace
cp .env.example .env
# Upravte .env — minimálně nastavte JWT_SECRET_KEY a ADMIN_PASSWORD
nano .env

# 4. Stažení vendor knihoven (Bootstrap, DataTables, jQuery, Ace Editor)
python scripts/download_vendors.py

# 5. Spuštění
python start.py
```

Aplikace běží na **http://localhost:8080**.

### Windows

```powershell
# 1. Klonování repozitáře
git clone https://github.com/your-org/UniForms.git
cd UniForms

# 2. Virtuální prostředí a závislosti
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Konfigurace
copy .env.example .env
# Upravte .env v textovém editoru — minimálně JWT_SECRET_KEY a ADMIN_PASSWORD
notepad .env

# 4. Stažení vendor knihoven
python scripts\download_vendors.py

# 5. Spuštění
python start.py
```

Aplikace běží na **http://localhost:8080**.

---

## 3. Výchozí přihlašovací údaje a první kroky

```
URL:       http://localhost:8080
Uživatel:  admin          (hodnota ADMIN_USERNAME z .env)
Heslo:     admin          (hodnota ADMIN_PASSWORD z .env)
```

> **Pozor:** Výchozí heslo `admin` je vhodné pouze pro lokální testování. Před nasazením pro více uživatelů ho ihned změňte: pravý horní roh → **Users** → editace účtu admin.

Po prvním přihlášení doporučené kroky:

1. Změňte heslo admina.
2. Otevřete **Settings** a upravte doménová nastavení (branding, terminologie).
3. V **Admin → Collections** vytvořte první kolekci.
4. Přidejte šablonu pro kolekci přes **Templates → New**.
5. Vytvořte první záznam tlačítkem na stránce šablon.

---

## 4. Konfigurační soubor `.env`

`.env` obsahuje tajné klíče a infrastrukturní nastavení. Nikdy ho neverzujte v gitu — je v `.gitignore`.

Vytvořte ho ze šablony:

```bash
cp .env.example .env
```

### Povinné klíče

```ini
# JWT tajný klíč — podpis autentizačních tokenů
# Vygenerujte: openssl rand -hex 32
JWT_SECRET_KEY=nahradte-silnym-klicem-min-32-znaku

# Přihlašovací údaje prvního admin účtu
# Použijí se POUZE při prvním spuštění (vytvoření databáze)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
```

### Volitelné klíče

```ini
JWT_EXPIRE_MINUTES=480         # platnost session v minutách (výchozí: 8 hodin)
JWT_ALGORITHM=HS256            # algoritmus podepisování tokenu
AUTH_PROVIDER=simple           # simple | ldap | oauth
DATABASE_PATH=data/uniforms.db # cesta k SQLite databázi
TIMEZONE=UTC                   # IANA název časového pásma (např. Europe/Prague)
DEFAULT_RECORDS_DIR=data/records
DEFAULT_SCHEMAS_DIR=data/schemas
DEFAULT_COLLECTIONS_DIR=data/collections
```

### Tabulka klíčů

| Klíč | ✓ | Popis |
|------|:-:|-------|
| `JWT_SECRET_KEY` | ✓ | Tajný klíč pro podepisování JWT tokenů (min. 32 náhodných znaků) |
| `ADMIN_USERNAME` | ✓ | Jméno prvního admin účtu (použije se jen při prvním startu) |
| `ADMIN_PASSWORD` | ✓ | Heslo prvního admin účtu — ihned změňte! |
| `JWT_EXPIRE_MINUTES` | | Platnost tokenu v minutách (výchozí: `480`) |
| `JWT_ALGORITHM` | | Algoritmus JWT (výchozí: `HS256`) |
| `AUTH_PROVIDER` | | Poskytovatel autentizace: `simple`, `ldap`, `oauth` (výchozí: `simple`) |
| `DATABASE_PATH` | | Cesta k SQLite souboru (výchozí: `data/uniforms.db`) |
| `TIMEZONE` | | IANA název časového pásma pro záznamy (výchozí: `UTC`) |
| `DEFAULT_RECORDS_DIR` | | Adresář pro záznamy (výchozí: `data/records`) |
| `DEFAULT_SCHEMAS_DIR` | | Adresář pro šablony (výchozí: `data/schemas`) |
| `DEFAULT_COLLECTIONS_DIR` | | Adresář pro kolekce (výchozí: `data/collections`) |

> **Poznámka:** `ADMIN_USERNAME` a `ADMIN_PASSWORD` se použijí pouze při prvním spuštění, pokud databáze neexistuje. Po vytvoření databáze se tyto klíče ignorují — správa uživatelů probíhá přes GUI.

---

## 5. Konfigurační soubor `uniforms.yaml`

`uniforms.yaml` obsahuje doménová nastavení aplikace — branding, terminologii, workflow a extensions. Lze ho verzovat; neobsahuje žádné tajné klíče (ty patří do `.env`).

Základ konfigurace:

```yaml
app:
  name: "UniForms"
  subtitle: "Universal Forms Engine"

terminology:
  record: "record"
  records: "records"
  record_id_label: "Record ID"
  template: "template"
  templates: "templates"
  new_record_btn: "New Record"
  record_owner_label: "Coordinator"
  take_over_btn: "Take Over"
  status_active: "Active"
  status_draft: "Draft"
  status_deprecated: "Deprecated"
  nav_dashboard: "Dashboard"
  nav_users: "Users"
  nav_settings: "Settings"

id:
  prefix: "REC"
  format: "{prefix}-{YYYYMM}-{rand:04d}"   # → REC-202603-0042

workflow:
  default_states:
    - id: new
      label: "New"
      color: secondary
    - id: open
      label: "Open"
      color: primary
    - id: in_progress
      label: "In Progress"
      color: warning
    - id: closed
      label: "Closed"
      color: success
  initial_state: new

extensions: []
```

### Přehled sekcí

| Sekce | Popis |
|-------|-------|
| `app` | Název a podtitulek aplikace zobrazované v UI |
| `terminology` | Překlad všech UI popisků — přizpůsobí aplikaci vaší doméně |
| `id` | Formát automaticky generovaných ID záznamů |
| `workflow` | Výchozí workflow stavy pro kolekce bez vlastního workflow |
| `extensions` | Seznam aktivovaných rozšíření (id + cesta) |

### Formát ID záznamu

Dostupné tokeny pro `id.format`:

| Token | Příklad | Popis |
|-------|---------|-------|
| `{prefix}` | `REC` | Hodnota z `id.prefix` |
| `{YYYYMM}` | `202603` | Rok a měsíc |
| `{DDMMYYYY}` | `16032026` | Den, měsíc, rok |
| `{YYYY}` | `2026` | Rok |
| `{MM}` | `03` | Měsíc |
| `{DD}` | `16` | Den |
| `{HHMM}` | `1430` | Hodiny a minuty |
| `{rand:04d}` | `0042` | Náhodné číslo (4 cifry s nulami) |

Kompletní dokumentovaný příklad najdete v `uniforms.yaml.example`.

---

## 6. Adresářová struktura po instalaci

```
UniForms/
├── app/                           zdrojový kód FastAPI aplikace
│   ├── api/                       REST API endpointy
│   ├── services/                  business logika (records, templates, ...)
│   ├── static/
│   │   ├── css/custom.css         vlastní styly (layout, sidebar)
│   │   ├── js/
│   │   │   ├── main.js            apiFetch() helper
│   │   │   └── uniforms.js        klientský renderer formulářů
│   │   └── vendor/                JS/CSS knihovny (staženo skriptem)
│   │       ├── bootstrap/
│   │       ├── bootstrap-icons/
│   │       ├── jquery/
│   │       ├── datatables/
│   │       └── ace/
│   ├── templates/                 Jinja2 HTML šablony
│   └── web/routes.py              webové routy (Jinja2 responses)
├── data/                          veškerá data aplikace (verzujte nebo zálohujte)
│   ├── collections/               definice kolekcí (YAML)
│   │   └── helpdesk.yaml
│   ├── schemas/                   YAML šablony per-kolekce
│   │   └── helpdesk/
│   │       └── it_request.yaml
│   ├── records/                   JSON záznamy per-kolekce (generuje se za běhu)
│   │   └── helpdesk/
│   │       └── REC-202603-0001.json
│   └── uniforms.db                SQLite databáze (uživatelé, nastavení, zámky)
├── docs/                          tato dokumentace
├── extensions/                    volitelná rozšíření
│   └── soc/                       SOC extension (šablony + renderery)
│       ├── extension.yaml
│       ├── js/
│       └── templates/
├── scripts/
│   └── download_vendors.py        stáhne JS/CSS knihovny do static/vendor/
├── .env                           tajné klíče (neverzovat!)
├── .env.example                   šablona pro .env
├── uniforms.yaml                  doménová konfigurace aplikace
├── uniforms.yaml.example          dokumentovaný příklad konfigurace
├── requirements.txt               Python závislosti
└── start.py                       spouštěč serveru
```

> **Tip:** Záloha aplikace = záloha adresáře `data/` + souborů `.env` a `uniforms.yaml`. Zdrojový kód lze kdykoli znovu naklonovat.

---

## 7. Spouštěč `start.py`

`start.py` automaticky vyhledá uvicorn v `.venv` (funguje na Linuxu i Windows) a spustí server. Pracovní adresář se nastaví na kořen projektu.

```bash
# Výchozí spuštění — bind na 127.0.0.1:8080
python start.py

# Síťový přístup — dostupné ze sítě
python start.py --host 0.0.0.0

# Jiný port
python start.py --port 8090

# Vývojový režim — automatický reload při změně kódu
python start.py --reload

# Kombinace přepínačů
python start.py --host 0.0.0.0 --port 8080 --reload
```

### Přepínače

| Přepínač | Výchozí | Popis |
|----------|---------|-------|
| `--host` | `127.0.0.1` | Adresa, na které server naslouchá |
| `--port` | `8080` | Port serveru |
| `--reload` | vypnuto | Automatický reload při změně Python souborů (pouze pro vývoj) |

Po spuštění server vypíše:

```
UniForms: http://127.0.0.1:8080
API docs:  http://127.0.0.1:8080/api/docs
Stop: Ctrl+C
```

Interaktivní dokumentace API (Swagger UI) je dostupná na `/api/docs`.

> **Pozor:** `--reload` nikdy nepoužívejte v produkci — výrazně zvyšuje spotřebu zdrojů a nespolehlivost.

---

## 8. Produkční nasazení (Linux + systemd + nginx)

Testováno na Rocky Linux 9 / RHEL 9. Na Debian/Ubuntu nahraďte `dnf` za `apt`.

### Krok 1 — Systémové závislosti

```bash
dnf install -y git python3.11 python3.11-pip nginx
```

### Krok 2 — Dedikovaný uživatel

```bash
useradd -m -s /bin/bash -d /opt/uniforms uniforms
```

### Krok 3 — Klonování a instalace

```bash
sudo -u uniforms git clone https://github.com/your-org/UniForms.git /opt/uniforms/app
sudo -u uniforms python3.11 -m venv /opt/uniforms/app/.venv
sudo -u uniforms bash -c "cd /opt/uniforms/app && .venv/bin/pip install -r requirements.txt"
```

### Krok 4 — Konfigurace

```bash
sudo -u uniforms cp /opt/uniforms/app/.env.example /opt/uniforms/app/.env

# Vygenerujte silný JWT klíč
openssl rand -hex 32

# Upravte .env
nano /opt/uniforms/app/.env
```

Minimální produkční `.env`:

```ini
JWT_SECRET_KEY=<vystup-z-openssl-rand>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<silne-heslo>
TIMEZONE=Europe/Prague
DATABASE_PATH=data/uniforms.db
```

Stažení vendor knihoven:

```bash
sudo -u uniforms bash -c "cd /opt/uniforms/app && .venv/bin/python scripts/download_vendors.py"
```

### Krok 5 — systemd service

Vytvořte `/etc/systemd/system/uniforms.service`:

```ini
[Unit]
Description=UniForms - Universal Forms Engine
After=network.target

[Service]
Type=simple
User=uniforms
Group=uniforms
WorkingDirectory=/opt/uniforms/app
ExecStart=/opt/uniforms/app/.venv/bin/python start.py
Restart=on-failure
RestartSec=5

# Omezení oprávnění
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
ReadWritePaths=/opt/uniforms/app/data

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable uniforms
systemctl start uniforms
systemctl status uniforms

# Sledování logů
journalctl -u uniforms -f
```

### Krok 6 — nginx jako reverzní proxy

Odstraňte výchozí blok `server {}` z `/etc/nginx/nginx.conf` a vytvořte `/etc/nginx/conf.d/uniforms.conf`.

#### Varianta A — Self-signed certifikát (interní prostředí)

```bash
mkdir -p /etc/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/uniforms.key \
  -out    /etc/nginx/ssl/uniforms.crt \
  -subj "/C=CZ/ST=Czech/L=Praha/O=Organizace/CN=uniforms"
chmod 600 /etc/nginx/ssl/uniforms.key
```

```nginx
# /etc/nginx/conf.d/uniforms.conf
server {
    listen 80;
    listen [::]:80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/uniforms.crt;
    ssl_certificate_key /etc/nginx/ssl/uniforms.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

```bash
nginx -t
systemctl enable nginx
systemctl start nginx
```

#### Varianta B — Let's Encrypt (veřejná doména)

Předpoklady: server přístupný z internetu na portech 80 a 443; DNS A záznam domény ukazuje na IP serveru.

```bash
dnf install -y epel-release
dnf install -y certbot python3-certbot-nginx

# Dočasná HTTP konfigurace pro vydání certifikátu
# (vložte do /etc/nginx/conf.d/uniforms.conf)
certbot --nginx -d forms.vasefirma.cz --redirect
```

Certbot automaticky ověří doménu, nainstaluje certifikát a nastaví automatické obnovování.

```bash
# Ověření automatického obnovení
certbot renew --dry-run
```

### Krok 7 — SELinux (Rocky Linux / RHEL)

Na systémech se SELinux v režimu enforcing musíte nginx explicitně povolit síťová spojení:

```bash
setsebool -P httpd_can_network_connect 1
```

Bez tohoto nastavení nginx vrátí **502 Bad Gateway**.

### Ověření nasazení

```bash
curl -sk https://127.0.0.1/ -o /dev/null -w "%{http_code}"
# Očekáváno: 302  (přesměrování na přihlášení)
```

---

## 9. Bezpečnostní checklist

Před zpřístupněním aplikace uživatelům ověřte:

- [ ] `JWT_SECRET_KEY` je náhodný řetězec min. 32 znaků (`openssl rand -hex 32`)
- [ ] Výchozí heslo admina bylo změněno přes GUI (Admin → Users)
- [ ] Aplikace je dostupná pouze přes HTTPS (nginx reverzní proxy)
- [ ] `.env` není verzován v gitu a má omezená oprávnění (`chmod 600 .env`)
- [ ] `uniforms.yaml` je nakonfigurován pro vaši doménu (název, terminologie, prefix ID)
- [ ] Nastaveno správné časové pásmo: `TIMEZONE=Europe/Prague`
- [ ] Vendor knihovny jsou staženy: `ls app/static/vendor/`
- [ ] systemd service je nastaven na automatický start: `systemctl is-enabled uniforms`
- [ ] Zálohovací cron job je nastaven: `crontab -l`
- [ ] SELinux nakonfigurován (RHEL/Rocky): `getsebool httpd_can_network_connect` → `on`

### Vestavěné bezpečnostní vrstvy

| Opatření | Popis |
|----------|-------|
| JWT httpOnly cookie | Auth token uložen v `httpOnly` cookie — nepřístupný z JavaScriptu; `samesite=lax` |
| CSRF ochrana | Každý `POST`/`PUT`/`PATCH` na `/api/v1/*` musí mít `Content-Type: application/json` — HTML formuláře blokuje s HTTP 415 |
| Security headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` |
| `X-Requested-With` | Všechna AJAX volání přes `apiFetch` odesílají `X-Requested-With: XMLHttpRequest` |
| Role-based access | Admin endpointy vyžadují roli `system_admin`; operace s kolekcí vyžadují `collection_admin` nebo `collection_user` |
| Bcrypt hesla | Hesla se nikdy neukládají v plaintextu; cost factor ~12 |
| XSS ochrana | Veškerý HTML obsah z JSON prochází sanitizací v `uniforms.js` |

---

## Reference

- Psaní šablon: [TEMPLATE_AUTHORING.md](TEMPLATE_AUTHORING.md)
- REST API: [API.md](API.md)
- Autentizace a role: [AUTH.md](AUTH.md)
- Frontend a renderer: [FRONTEND.md](FRONTEND.md)
