# UniForms – Instalace a nasazení

UniForms je webová aplikace pro strukturovaný sběr dat a správu záznamů prostřednictvím formulářů definovaných v YAML. Uživatelé vyplňují formuláře v prohlížeči; YAML šablony definují strukturu každého typu záznamu.

Určeno správcům systémů a vývojářům nasazujícím aplikaci.

**Požadavky:** Python 3.11 nebo novější, Git.

---

## Jak to funguje?

```
data/collections/*.yaml     — definice kolekcí (terminologie, workflow, role)
data/schemas/{coll}/*.yaml  — YAML šablony organizované per-kolekce
data/records/{coll}/*.json  — JSON záznamy organizované per-kolekce
data/uniforms.db            — SQLite (uživatelé, nastavení, collection_roles)

         ┌──────────────────────┐
         │      start.py        │  spustí uvicorn na portu 8080
         └──────────┬───────────┘
                    │
         ┌──────────▼───────────┐
         │    FastAPI aplikace  │  REST API + Jinja2 webové routy
         │                      │
         │  ┌────────────────┐  │
         │  │ JWT middleware │  │  ověření tokenu z httpOnly cookie
         │  └────────────────┘  │
         └──────────┬───────────┘
                    │
         ┌──────────▼───────────┐
         │     Prohlížeč        │  Bootstrap 5, uniforms.js renderer
         └──────────────────────┘
```

Veškerá data jsou lokální — žádný cloud, žádná externí databáze. Záloha = záloha adresáře `data/`.

---

## Rychlá instalace — lokální spuštění

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

# 4. Stažení vendor knihoven (Bootstrap, DataTables, jQuery, Ace Editor)
python scripts/download_vendors.py

# 5. Spuštění
python start.py
```

Aplikace je dostupná na **http://localhost:8080**.

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
# Upravte .env — minimálně nastavte JWT_SECRET_KEY a ADMIN_PASSWORD

# 4. Stažení vendor knihoven
python scripts\download_vendors.py

# 5. Spuštění
python start.py
```

---

## Výchozí přihlášení

```
URL:      http://localhost:8080
Uživatel: admin
Heslo:    admin   (nebo dle ADMIN_PASSWORD v .env)
```

> Heslo změňte ihned po prvním přihlášení: nabídka v pravém horním rohu → **Users** → editace účtu admin.

---

## Konfigurace

### `.env` — tajné klíče a infrastruktura

Vytvořte `.env` ze souboru `.env.example`. Povinné klíče:

```ini
# JWT tajný klíč — VŽDY změňte před nasazením!
# Vygenerujte: openssl rand -hex 32
JWT_SECRET_KEY=nahodny-retezec-min-32-znaku

# Přihlašovací údaje prvního admin účtu (použity pouze při prvním spuštění)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
```

Volitelné klíče s výchozími hodnotami:

```ini
# Platnost JWT tokenu v minutách (výchozí: 480 = 8 hodin)
# JWT_EXPIRE_MINUTES=480

# Poskytovatel autentizace (výchozí: simple — username/password z SQLite)
# AUTH_PROVIDER=simple

# Cesta k SQLite databázi (výchozí: data/uniforms.db)
# DATABASE_PATH=data/uniforms.db

# Časové pásmo pro časová razítka v záznamech (IANA název, výchozí: UTC)
# TIMEZONE=Europe/Prague

# Výchozí adresáře pro ukládání dat (lze také změnit v GUI → Settings)
# DEFAULT_RECORDS_DIR=data/records
# DEFAULT_SCHEMAS_DIR=data/schemas
# DEFAULT_COLLECTIONS_DIR=data/collections
```

| Klíč | ✓ | Popis |
|------|---|-------|
| `JWT_SECRET_KEY` | ✓ | Tajný klíč pro podepisování JWT tokenů (min. 32 znaků) |
| `ADMIN_USERNAME` | ✓ | Uživatelské jméno prvního admin účtu |
| `ADMIN_PASSWORD` | ✓ | Heslo prvního admin účtu |
| `JWT_EXPIRE_MINUTES` | | Platnost tokenu v minutách (výchozí: 480) |
| `AUTH_PROVIDER` | | Poskytovatel autentizace: `simple`, `oauth`, `ldap` (výchozí: `simple`) |
| `DATABASE_PATH` | | Cesta k SQLite souboru (výchozí: `data/uniforms.db`) |
| `TIMEZONE` | | IANA název časového pásma (výchozí: `UTC`) |
| `DEFAULT_RECORDS_DIR` | | Adresář pro záznamy (výchozí: `data/records`) |
| `DEFAULT_SCHEMAS_DIR` | | Adresář pro šablony (výchozí: `data/schemas`) |
| `DEFAULT_COLLECTIONS_DIR` | | Adresář pro kolekce (výchozí: `data/collections`) |

> Po prvním spuštění se admin účet uloží do databáze. `ADMIN_USERNAME` a `ADMIN_PASSWORD` se použijí znovu pouze v případě, že databáze neexistuje.

### `uniforms.yaml` — doménová konfigurace

Doménová nastavení patří do `uniforms.yaml`, ne do `.env`. Záměr: infrastrukturní tajné klíče jsou v `.env`, doménová konfigurace (jak se aplikace jmenuje, jak se záznamy jmenují, jaké workflow stavy existují) je v `uniforms.yaml` a lze ji verzovat zvlášť.

```yaml
app:
  name: "UniForms"
  subtitle: "Universal Forms Engine"

terminology:
  record: "zaznam"
  records: "zaznamy"
  template: "sablona"
  templates: "sablony"

id:
  prefix: "REC"
  format: "{prefix}-{YYYYMM}-{rand:04d}"

extensions: []
```

Kompletní referenci najdete v souboru `uniforms.yaml.example`.

---

## start.py — možnosti spuštění

`start.py` automaticky vyhledá uvicorn uvnitř `.venv` (Linux i Windows) a spustí server.

```bash
# Lokální přístup (výchozí — bind na 127.0.0.1:8080)
python start.py

# Síťový přístup (všechna rozhraní)
python start.py --host 0.0.0.0

# Vývojový režim s automatickým reloadem
python start.py --reload

# Kombinace — síťový přístup s reloadem a jiným portem
python start.py --host 0.0.0.0 --port 8080 --reload
```

---

## Ruční start / stop na Windows

Tato sekce popisuje správu procesu serveru ručně v shellu — bez Windows Service ani Task Scheduleru.

### Spuštění na popředí

Nejjednodušší způsob. Server vypisuje logy přímo do terminálu; zavřením okna nebo **Ctrl+C** ho zastavíte.

**PowerShell nebo CMD:**

```powershell
cd C:\cesta\k\UniForms
python start.py
```

Po úspěšném startu uvidíte:

```
Forms4SOC: http://127.0.0.1:8080
API docs:  http://127.0.0.1:8080/api/docs
Stop: Ctrl+C

INFO:     Started server process [12345]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8080 (Press CTRL+C to quit)
```

Aplikace je dostupná na **http://localhost:8080**.

> **Okno musí zůstat otevřené.** Zavřením okna nebo odhlášením ze systému se server zastaví.

---

### Spuštění na pozadí (PowerShell)

Pokud chcete server spustit na pozadí a zavřít terminál, použijte `Start-Process`:

```powershell
cd C:\cesta\k\UniForms

# Spuštění na pozadí — logy do souboru uniforms.log
Start-Process -FilePath "python" `
    -ArgumentList "start.py" `
    -WorkingDirectory (Get-Location) `
    -RedirectStandardOutput "uniforms.log" `
    -RedirectStandardError "uniforms.log" `
    -NoNewWindow
```

Po spuštění ověřte, zda server běží:

```powershell
# Ověření — musí vrátit "302"
(Invoke-WebRequest -Uri "http://127.0.0.1:8080/" -MaximumRedirection 0 -ErrorAction SilentlyContinue).StatusCode

# Nebo zjistěte PID procesu
Get-NetTCPConnection -LocalPort 8080 -State Listen | Select-Object -ExpandProperty OwningProcess
```

Logy sledujte příkazem:

```powershell
Get-Content uniforms.log -Wait -Tail 20
```

---

### Zastavení serveru

**Možnost 1 — Ctrl+C v terminálu** (pokud server běží na popředí)

**Možnost 2 — zastavení podle PID:**

```powershell
# 1. Zjistěte PID procesu poslouchajícího na portu 8080
$pid = (Get-NetTCPConnection -LocalPort 8080 -State Listen).OwningProcess
Write-Host "PID serveru: $pid"

# 2. Zastavte proces
Stop-Process -Id $pid -Force
```

**Možnost 3 — zastavení podle názvu procesu** (pokud víte, že žádný jiný uvicorn neběží):

```powershell
Stop-Process -Name uvicorn -Force
```

Ověření, že server skutečně skončil:

```powershell
# Musí vrátit prázdný výstup
Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
```

---

### Restart (stop + start)

```powershell
cd C:\cesta\k\UniForms

# Zastavit existující instanci (pokud běží)
$existing = (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue).OwningProcess
if ($existing) { Stop-Process -Id $existing -Force; Start-Sleep -Seconds 1 }

# Spustit znovu
python start.py
```

---

### Nejčastější chyby při spouštění

| Chyba | Příčina | Řešení |
|-------|---------|--------|
| `error while attempting to bind on address ... [WinError 10048]` | Port 8080 je obsazen jiným procesem | Zastavte starý proces (viz výše) nebo spusťte na jiném portu: `python start.py --port 8081` |
| `uvicorn nenalezen` | Virtuální prostředí není aktivováno nebo závislosti nejsou nainstalovány | Spusťte `pip install -r requirements.txt` uvnitř `.venv` |
| `ModuleNotFoundError` | Python spuštěn mimo adresář projektu | Vždy spouštějte příkaz z kořenového adresáře `UniForms/` |
| Stránka se nenačítá, `curl` vrací `000` | Server ještě startuje nebo havaroval | Počkejte 2–3 sekundy; zkontrolujte logy |

---

## Adresářová struktura po instalaci

```
UniForms/
├── app/                        — zdrojový kód aplikace
├── data/
│   ├── collections/            — definice kolekcí (YAML)
│   │   ├── soc.yaml
│   │   └── zverimex.yaml
│   ├── schemas/                — šablony organizované per-kolekce
│   │   ├── soc/
│   │   │   ├── phishing.yaml
│   │   │   └── malware.yaml
│   │   └── zverimex/
│   │       └── animal_card.yaml
│   ├── records/                — záznamy per-kolekce (vytváří se automaticky)
│   │   ├── soc/
│   │   │   └── SOC-202603-0001.json
│   │   └── zverimex/
│   │       └── ZVE-202603-0001.json
│   └── uniforms.db             — SQLite databáze (vytváří se automaticky)
├── docs/                       — tato dokumentace
├── extensions/                 — volitelná rozšíření
│   └── soc/                    — SOC rozšíření (šablony, renderery)
│       └── templates/
├── scripts/
│   └── download_vendors.py     — stáhne JS/CSS knihovny
├── .env                        — konfigurace (vytvoř z .env.example)
├── uniforms.yaml               — globální konfigurace aplikace
├── requirements.txt
└── start.py                    — startovací skript
```

---

## Bezpečnostní poznámky

Následující bezpečnostní vrstvy jsou aktivní ve výchozím nastavení:

| Opatření | Popis |
|----------|-------|
| JWT httpOnly cookie | Auth token uložen v httpOnly cookie `uniforms_token` — nepřístupný z JavaScriptu; `samesite=lax` |
| SecurityMiddleware | Každý POST/PUT/PATCH na `/api/v1/*` musí mít `Content-Type: application/json` — blokuje CSRF přes HTML formuláře (HTTP 415) |
| Security headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` |
| `X-Requested-With` | Všechna AJAX volání přes `apiFetch` odesílají `X-Requested-With: XMLHttpRequest` |
| Role-based access | Admin endpointy vyžadují globální roli `system_admin`; operace s kolekcí vyžadují příslušnou roli kolekce (`collection_admin` nebo `collection_user`) |
| Bcrypt hesla | Cost factor ~12; hesla se nikdy neukládají v plaintextu |

**Doporučení pro produkci:**
- Nastavte silný `JWT_SECRET_KEY` (minimálně 32 náhodných znaků)
- Provozujte za HTTPS reverzní proxy (nginx) — viz sekce o produkčním nasazení
- Změňte výchozí heslo admina ihned po prvním přihlášení
- Nastavte `TIMEZONE` dle lokality serveru (např. `Europe/Prague`)

---

## Aktualizace

```bash
cd /opt/uniforms/app
sudo -u uniforms git pull
sudo -u uniforms .venv/bin/pip install -r requirements.txt
sudo systemctl restart uniforms
```

---

## Produkční nasazení na Linuxu (Rocky Linux 9 / RHEL)

Testováno na **Rocky Linux 9.2**. Stejný postup platí pro RHEL 9, AlmaLinux 9 a kompatibilní distribuce. Na Debian/Ubuntu nahraďte `dnf` za `apt`; Python 3.11 může být dostupný přímo bez přidání repozitáře.

### 1. Systémové závislosti

Rocky Linux 9 dodává Python 3.9 ve výchozím stavu. Python 3.11 je dostupný v repozitáři AppStream:

```bash
dnf install -y git python3.11 python3.11-pip
python3.11 --version   # ověření: Python 3.11.x
```

### 2. Dedikovaný uživatel a adresář

Spusťte aplikaci pod dedikovaným uživatelem `uniforms` s omezenými oprávněními:

```bash
useradd -m -s /bin/bash -d /opt/uniforms uniforms
```

### 3. Klonování repozitáře

```bash
sudo -u uniforms git clone https://github.com/your-org/UniForms.git /opt/uniforms/app
```

### 4. Virtuální prostředí a závislosti

```bash
sudo -u uniforms python3.11 -m venv /opt/uniforms/app/.venv
sudo -u uniforms bash -c "cd /opt/uniforms/app && .venv/bin/pip install -r requirements.txt"
```

### 5. Konfigurace

```bash
sudo -u uniforms cp /opt/uniforms/app/.env.example /opt/uniforms/app/.env

# Vygenerujte silný JWT klíč
openssl rand -hex 32

# Upravte .env — nastavte JWT_SECRET_KEY, ADMIN_PASSWORD a TIMEZONE
nano /opt/uniforms/app/.env
```

Minimální produkční `.env`:

```ini
JWT_SECRET_KEY=<vystup-z-openssl-rand>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<silne-heslo>
TIMEZONE=Europe/Prague
DATABASE_PATH=data/uniforms.db
DEFAULT_RECORDS_DIR=data/records
DEFAULT_SCHEMAS_DIR=data/schemas
DEFAULT_COLLECTIONS_DIR=data/collections
```

Upravte `uniforms.yaml` pro doménovou konfiguraci:

```bash
nano /opt/uniforms/app/uniforms.yaml
```

### 6. Stažení vendor knihoven

```bash
sudo -u uniforms bash -c "cd /opt/uniforms/app && .venv/bin/python scripts/download_vendors.py"
```

Stáhne Bootstrap, Bootstrap Icons, jQuery, DataTables a Ace Editor do `app/static/vendor/`.

### 7. systemd service

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

# Logy
journalctl -u uniforms -f
```

### 8. Nginx jako reverzní proxy

Nainstalujte nginx a odstraňte výchozí blok `server {}` z `/etc/nginx/nginx.conf` (blok `server { listen 80; ... }` uvnitř sekce `http`), aby nedocházelo ke konfliktům:

```bash
dnf install -y nginx
```

V `/etc/nginx/nginx.conf` smažte nebo zakomentujte celý výchozí blok `server {}`. Poté vytvořte `/etc/nginx/conf.d/uniforms.conf` podle jedné z variant níže.

---

#### Option A — Self-signed certifikát (interní / testovací prostředí)

Vhodné pro interní nasazení bez veřejné domény. Prohlížeč zobrazí varování o nedůvěryhodném certifikátu — to je očekávané chování.

**Vygenerování certifikátu:**

```bash
mkdir -p /etc/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/uniforms.key \
  -out /etc/nginx/ssl/uniforms.crt \
  -subj "/C=CZ/ST=Czech/L=Praha/O=Organizace/CN=uniforms"
chmod 600 /etc/nginx/ssl/uniforms.key
```

**`/etc/nginx/conf.d/uniforms.conf`:**

```nginx
# Přesměrování HTTP na HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name _;
    return 301 https://$host$request_uri;
}

# HTTPS reverzní proxy pro UniForms
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

Aplikace dostupná na `https://<ip-serveru>`.

---

#### Option B — Let's Encrypt (produkce s veřejnou doménou)

Vhodné pro veřejně přístupná nasazení s registrovanou doménou. Certifikát je důvěryhodný, zdarma a automaticky se obnovuje.

**Předpoklady:**
- Server přístupný z internetu na portech 80 a 443
- DNS A záznam domény ukazuje na IP serveru
- Připravený název domény (např. `forms.vasefirma.cz`)

**Instalace certbotu:**

```bash
dnf install -y epel-release
dnf install -y certbot python3-certbot-nginx
```

**Příprava nginx před vydáním certifikátu:**

```nginx
# /etc/nginx/conf.d/uniforms.conf (dočasná konfigurace)
server {
    listen 80;
    listen [::]:80;
    server_name forms.vasefirma.cz;

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

**Vydání certifikátu:**

```bash
certbot --nginx -d forms.vasefirma.cz --redirect
```

Certbot automaticky:
- Ověří vlastnictví domény přes HTTP challenge
- Stáhne a nainstaluje certifikát do `/etc/letsencrypt/live/<domena>/`
- Aktualizuje nginx konfiguraci (přidá SSL direktivy a přesměrování HTTP→HTTPS)
- Nastaví systemd timer pro automatické obnovování certifikátu

**Ověření automatického obnovení:**

```bash
certbot renew --dry-run
```

> Let's Encrypt certifikát je platný 90 dní. Certbot ho obnovuje automaticky. Certifikáty nejsou součástí zálohy dat aplikace — při obnově serveru spusťte `certbot --nginx -d <domena>` znovu.

---

### 9. SELinux (Rocky Linux / RHEL)

Na systémech se SELinux v režimu enforcing (výchozí na RHEL/Rocky) nginx nemůže vytvářet síťová spojení bez explicitního povolení. Bez tohoto nastavení nginx vrací **502 Bad Gateway**:

```bash
setsebool -P httpd_can_network_connect 1
```

Ověření:

```bash
curl -sk https://127.0.0.1/ -o /dev/null -w "%{http_code}"
# Očekáváno: 302 (přesměrování na přihlášení)
```

### 10. První přihlášení

Přihlaste se s výchozími přihlašovacími údaji:

```
Uživatel: admin
Heslo:    admin   (nebo dle ADMIN_PASSWORD v .env)
```

Okamžitě změňte heslo: **nabídka vpravo nahoře → Users → editace účtu admin**.

---

## Zálohovací skript

Vytvořte `/opt/uniforms/backup.sh`.

Obsah zálohy se liší podle SSL varianty:
- **Option A (self-signed):** záloha zahrnuje certifikát a klíč z `/etc/nginx/ssl/`
- **Option B (Let's Encrypt):** certifikát se nezálohuje — certbot ho spravuje; při obnově serveru vydejte nový

**Option A — se self-signed certifikátem:**

```bash
#!/bin/bash
# UniForms — zálohovací skript (self-signed SSL)
set -euo pipefail

BACKUP_DIR="/opt/uniforms/backups"
APP_DIR="/opt/uniforms/app"
DATE=$(date +%Y%m%d_%H%M%S)
ARCHIVE="${BACKUP_DIR}/uniforms_${DATE}.tar.gz"
KEEP_DAYS=30

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Spouštím zálohu UniForms..."

tar -czf "${ARCHIVE}" \
    --ignore-failed-read \
    "${APP_DIR}/data" \
    "${APP_DIR}/.env" \
    "${APP_DIR}/uniforms.yaml" \
    /etc/nginx/conf.d/uniforms.conf \
    /etc/nginx/ssl/uniforms.crt \
    /etc/nginx/ssl/uniforms.key \
    /etc/systemd/system/uniforms.service

SIZE=$(du -sh "${ARCHIVE}" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Záloha vytvořena: ${ARCHIVE} (${SIZE})"

DELETED=$(find "${BACKUP_DIR}" -name "uniforms_*.tar.gz" -mtime +${KEEP_DAYS} -print -delete | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Odstraněno ${DELETED} starých záloh (>${KEEP_DAYS} dní)"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Hotovo."
```

**Option B — s Let's Encrypt certifikátem:**

```bash
#!/bin/bash
# UniForms — zálohovací skript (Let's Encrypt SSL)
set -euo pipefail

BACKUP_DIR="/opt/uniforms/backups"
APP_DIR="/opt/uniforms/app"
DATE=$(date +%Y%m%d_%H%M%S)
ARCHIVE="${BACKUP_DIR}/uniforms_${DATE}.tar.gz"
KEEP_DAYS=30

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Spouštím zálohu UniForms..."

tar -czf "${ARCHIVE}" \
    --ignore-failed-read \
    "${APP_DIR}/data" \
    "${APP_DIR}/.env" \
    "${APP_DIR}/uniforms.yaml" \
    /etc/nginx/conf.d/uniforms.conf \
    /etc/systemd/system/uniforms.service

SIZE=$(du -sh "${ARCHIVE}" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Záloha vytvořena: ${ARCHIVE} (${SIZE})"

DELETED=$(find "${BACKUP_DIR}" -name "uniforms_*.tar.gz" -mtime +${KEEP_DAYS} -print -delete | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Odstraněno ${DELETED} starých záloh (>${KEEP_DAYS} dní)"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Hotovo."
```

```bash
# Vytvoření adresáře pro zálohy, nastavení oprávnění, první záloha
mkdir -p /opt/uniforms/backups
chmod +x /opt/uniforms/backup.sh
/opt/uniforms/backup.sh

# Nastavení denního cronu ve 02:00
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/uniforms/backup.sh >> /opt/uniforms/backups/backup.log 2>&1") | crontab -
```

Zálohy starší než 30 dní se mažou automaticky. Log záloh: `/opt/uniforms/backups/backup.log`.

---

## Post-install checklist

Po dokončení všech kroků ověřte:

- [ ] Aplikace běží: `systemctl is-active uniforms`
- [ ] Nginx běží: `systemctl is-active nginx`
- [ ] HTTPS odpovídá: `curl -sk https://127.0.0.1/ -o /dev/null -w "%{http_code}"` → `302`
- [ ] SELinux nakonfigurován: `getsebool httpd_can_network_connect` → `on`
- [ ] Silný JWT klíč nastaven v `.env`
- [ ] Heslo admina změněno v GUI aplikace
- [ ] `uniforms.yaml` nakonfigurován pro vaši doménu
- [ ] Vendor knihovny staženy: `ls /opt/uniforms/app/app/static/vendor/`
- [ ] První záloha provedena: `ls /opt/uniforms/backups/`
- [ ] Cron job nastaven: `crontab -l`
- [ ] **(Option B)** Automatické obnovování ověřeno: `certbot renew --dry-run`

---

## Reference

- Konfigurace šablon: [TEMPLATE_AUTHORING.md](TEMPLATE_AUTHORING.md)
- REST API: [API.md](API.md)
- Bezpečnost a autentizace: [AUTH.md](AUTH.md)
- Renderování na frontendu: [UNIFORMS_JS.md](UNIFORMS_JS.md)
