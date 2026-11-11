#!/usr/bin/env python3
"""Demo data – Autobusová doprava Kladno (fictional): 10 SOC incidents + 10 data sources.

Usage:
    UNIFORMS_URL=http://127.0.0.1:8080 UNIFORMS_USER=admin python scripts/seed_demo_adk.py <password>

Creates records through the REST API (same structure as records made in the UI), then
back-dates created_at directly in data/records/ so the dashboard looks lived-in.
Requires the target collections/templates to exist (they ship in data/collections, data/schemas).
"""
import os
import json, sys, urllib.request, http.cookiejar, random
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = os.environ.get("UNIFORMS_URL", "http://127.0.0.1:8080").rstrip("/")
RECORDS_DIR = Path(__file__).resolve().parents[1] / "data" / "records"
PW = sys.argv[1]
random.seed(42)

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def api(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with op.open(req) as r:
        txt = r.read()
        return json.loads(txt) if txt else None

api("POST", "/api/v1/auth/login", {"username": os.environ.get("UNIFORMS_USER", "admin"), "password": PW})

DOM = "adk.example"
def mail(name):  # "Honza Nesnídal" -> honza.nesnidal@adk.example
    import unicodedata
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return n.replace(" ", ".") + "@" + DOM

PEOPLE_CONTACTS = ["Service Desk ADK (Dispečink IT)", "Petr Stoural", "Jakub Runda", "Pavel Louda",
                   "Ing. Miroslava Přísná", "Bohumil Kabelka", "Vlasta Účetní", "Mgr. Radim Paragraf",
                   "Karel Klíčník", "Jarmila Jízdní", "Zdeněk Záloha", "Drahomír Data"]

# ── helpers ──────────────────────────────────────────────────────────────────
def walk(sections):
    for s in sections:
        yield s
        yield from walk((s.get("sections") or []) + (s.get("subsections") or []))

def set_fields(data, values):
    left = dict(values)
    for s in walk(data["sections"]):
        for f in s.get("fields") or []:
            if f["key"] in left:
                v = left.pop(f["key"])
                if f.get("type") == "select" and v is not None:
                    m = [o for o in f["options"] if o == v] or [o for o in f["options"] if o.startswith(v)]
                    if len(m) != 1:
                        raise SystemExit(f"select {f['key']}: '{v}' matches {m} of {f['options']}")
                    v = m[0]
                f["value"] = v
    if left:
        raise SystemExit(f"unknown fields: {list(left)}")

def sec(data, sid):
    return next(s for s in walk(data["sections"]) if s["id"] == sid)

def fill_checklists(data, ratio, notes):
    """Mark first `ratio` of steps done; attach analyst notes round-robin."""
    notes = list(notes)
    for s in walk(data["sections"]):
        if s.get("type") != "checklist":
            continue
        steps = [st for g in s.get("step_groups", []) for st in g.get("steps", [])]
        n = round(len(steps) * ratio)
        for i, st in enumerate(steps):
            st["done"] = i < n
            if st["done"] and notes and i % 2 == 0:
                st["analyst_note"] = notes.pop(0)

def fill_soc_tables(data, ratio, owner, comm_note, extra_actions, assets):
    for row in sec(data, "contacts")["rows"]:
        i = sec(data, "contacts")["rows"].index(row)
        name = owner if "oordin" in (row.get("system_role") or "") else PEOPLE_CONTACTS[i % len(PEOPLE_CONTACTS)]
        row["name"] = name
        row["email"] = "servicedesk@" + DOM if name.startswith("Service") else mail(name.replace("Ing. ", "").replace("Mgr. ", ""))
        row["phone"] = f"+420 312 {random.randint(100,999)} {random.randint(100,999)}"
    rows = sec(data, "containment_remediation")["rows"]
    n = round(len(rows) * ratio)
    for i, r in enumerate(rows):
        r["status"] = "Provedeno" if i < n else ("Probíhá" if i == n and ratio < 1 else ("Čeká" if ratio < 1 else "Není nutné provést"))
    for r in sec(data, "communication")["rows"][: (len(sec(data, "communication")["rows"]) if ratio >= 1 else 2)]:
        r["note"] = comm_note
    sec(data, "additional_actions")["rows"] = [
        {"action": a, "cooperation": c, "status": st} for a, c, st in extra_actions]
    sec(data, "affected_assets")["rows"] = [
        dict(zip(["asset_name", "fqdn", "asset_ip", "asset_type", "regulated_service", "notes"], a)) for a in assets]

def ts(days_ago, hh, mm=0):
    d = (datetime(2026, 11, 11) - timedelta(days=days_ago)).replace(hour=hh, minute=mm)
    return d.strftime("%Y-%m-%dT%H:%M"), d

created = []

def create(collection, template_id, status, values, days_ago, hour, extra=None):
    rec = api("POST", f"/api/v1/records/{collection}/", {"template_id": template_id})
    rid = rec["record_id"]
    data = rec["data"]
    set_fields(data, values)
    if extra:
        extra(data)
    api("PATCH", f"/api/v1/records/{collection}/{rid}", {"status": status, "data": data})
    _, dt = ts(days_ago, hour)
    created.append((collection, rid, dt, status, values.get("case_title") or values.get("source_name")))

# ═════════════════════════════════════════════════════════════════════════════
#  SOC – 10 UIB
# ═════════════════════════════════════════════════════════════════════════════
CLOSE_COMMON = dict(reporter_notified="Ano", nukib_notification_required="Není vyžadována",
                    ucl_notification_required="Není vyžadována")

def soc(template, status, owner, days, hour, title, sub, det, l2, closure=None, ratio=0.0,
        comm="", extra_actions=(), assets=(), notes=()):
    values = {"case_title": title, "record_owner": owner, "mitre_subtechnique": sub, **det, **l2}
    if closure:
        values.update(CLOSE_COMMON); values.update(closure)
    def ex(data):
        fill_checklists(data, ratio, notes)
        fill_soc_tables(data, ratio, owner, comm, extra_actions, assets)
    create("soc", template, status, values, days, hour, ex)

# 1 ─ Phishing: výherní elektrokoloběžka
r, _ = ts(38, 7, 42)
soc("uib-phishing-v2", "closed", "Petr Stoural", 38, 7,
    "Phishing – „Vyhrál jste elektrokoloběžku“ · uživatel: Honza Nesnídal · klikl, heslo nezadal (šetřil čas na snídani)",
    "T1566.002",
    dict(source_type="Hlášení zaměstnancem", reported_at=r, reporter_name="Honza Nesnídal",
         reporter_department="Dispečink", reporter_contact="honza.nesnidal@adk.example, kl. 214",
         affected_user="honza.nesnidal@adk.example", user_action="Klikl na odkaz, ale nezad",
         attachment_or_link="Odkaz", url_clicked="Ano",
         description_by_reporter="Přišel mi mail, že jsem vyhrál elektrokoloběžku jako věrný cestující. "
             "Kliknul jsem, ale chtěli číslo karty na poštovné 49 Kč, tak jsem to zavřel – stejně jezdím autobusem.",
         detection_tool="Microsoft Defender for Office 365", alert_id="DfO-2026-10-04-0815",
         alert_description="URL click verdict: Phishing (SafeLinks pozdní detekce). Kampaň zasáhla 14 schránek, klikl 1 uživatel."),
    dict(phishing_scenario="Scénář B", credential_submitted="Ne – potvrzeno", l2_initial_priority="P3"),
    dict(final_classification="True Positive", impact_level="Nízká", impact_primary_service="Dostupné bez omezení",
         impact_scope="Individuální", impact_duration="Žádný výpadek", impact_data="Žádný dopad na data",
         root_cause="Uživatel podlehl lákavé nabídce elektrokoloběžky. Údaje nezadal, protože měl hlad a spěchal.",
         actions_taken="Blokace domény koloběžky-zdarma.example, purge kampaně ze 14 schránek, kontrola sign-in logů (čisté).",
         recommendations="Opakované školení phishingu. Doporučeno snídat před otevřením pošty – zvyšuje ostražitost.",
         related_service_requests="TIS-48211", related_security_events="DfO-2026-10-04-0815",
         closed_at=ts(37, 15)[0],
         phishing_scenario_final="Scénář B", user_action_final="Klikl na odkaz, nezadal",
         email_vector_final="Masový phishing"),
    ratio=1.0, comm="Uživatel informován osobně u kávovaru.",
    extra_actions=[("Purge e-mailu z 14 schránek (Threat Explorer)", "Správce M365", "Provedeno"),
                   ("Nahlášení domény do Microsoft (submission)", "CSIRT", "Provedeno")],
    assets=[("NB-DISP-07", "nb-disp-07.adk.example", "10.20.4.57", "Notebook", "Ne", "Notebook dispečera, Defender čistý")],
    notes=["Ověřeno telefonicky – uživatel odkaz otevřel, kartu nezadal.", "Sign-in logy bez anomálií."])

# 2 ─ Phishing: faktura PHM.zip
r, _ = ts(3, 9, 15)
soc("uib-phishing-v2", "in_progress", "Jakub Runda", 3, 9,
    "Phishing – „Faktura za naftu 2026-10.zip“ · uživatel: Otakar Nevečeřel · otevřel přílohu, Defender zasáhl",
    "T1566.001",
    dict(source_type="Automatizovaná detekce", reported_at=r, reporter_name="Defender XDR (automat)",
         reporter_department="—", reporter_contact="—", affected_user="otakar.nevecerel@adk.example",
         user_action="Otevřel přílohu (bez", attachment_or_link="Přílohu", url_clicked="Ne – neklikl",
         description_by_reporter="Uživatel uvádí: „Faktury za naftu otevírám vždycky, to je moje práce. Jen tahle byla v zipu s heslem 1234.“",
         alert_timestamp=r, detection_tool="Microsoft Defender for Endpoint", alert_id="MDE-ALERT-77812",
         affected_asset_auto="PC-UCT-03",
         alert_description="Suspicious script execution from archive: Faktura_nafta_2026-10.js – blokováno, proces ukončen."),
    dict(phishing_scenario="Scénář D", credential_submitted="Ne – potvrzeno", l2_initial_priority="P2"),
    ratio=0.5, comm="Uživatel informován, ať zatím faktury za naftu neotevírá a raději si dá večeři.",
    extra_actions=[("Full scan PC-UCT-03 a kontrola persistence", "Správce koncových stanic", "Probíhá"),
                   ("Ověřit u dodavatele PHM, zda opravdu posílá zipy s heslem", "Účtárna", "Čeká")],
    assets=[("PC-UCT-03", "pc-uct-03.adk.example", "10.20.8.33", "Desktop", "Ne", "Účtárna – izolováno přes MDE")],
    notes=["Hash přílohy na VirusTotal 41/70 – AsyncRAT loader.", "Izolace stanice potvrzena v 9:31."])

# 3 ─ BEC: dárkové karty od „ředitele“
r, _ = ts(25, 6, 5)
soc("uib-bec-v2", "closed", "Pavel Louda", 25, 6,
    "BEC – „ředitel“ žádá 50 ks dárkových karet · uživatel: Antonín Dochvilný · nakoupit nestihl, byl v práci příliš brzy",
    "T1566.002",
    dict(source_type="Hlášení zaměstnancem", reported_at=r, reporter_name="Antonín Dochvilný",
         reporter_department="Nákup", reporter_contact="antonin.dochvilny@adk.example",
         affected_user="antonin.dochvilny@adk.example", attachment_or_link="Ne",
         description_by_reporter="V 5:58 mi psal pan ředitel z Gmailu, ať urgentně koupím 50 dárkových karet. "
             "Byl jsem v práci jako vždy první, ale obchody ještě neotevřely. Pak jsem si všiml, že pan ředitel nikdy nevstává před osmou.",
         detection_tool="—", alert_id="—",
         alert_description="Hlášeno uživatelem tlačítkem Report Message."),
    dict(bec_action_taken="Ne – žádost nesplněna", payment_stoppable="Netýká se", l2_initial_priority="P3"),
    dict(final_classification="True Positive", impact_level="Nízká", impact_primary_service="Netýká se",
         impact_scope="Individuální", impact_duration="Žádný výpadek", impact_data="Žádný dopad na data",
         root_cause="Typický CEO fraud z free-mail adresy. Útočník netušil, že pan Dochvilný je v práci dřív, než otevřou obchody.",
         actions_taken="Blokace odesílatele, varování všem zaměstnancům Nákupu, banner [EXTERNAL] v Exchange posílen.",
         recommendations="Zachovat dochvilnost pana Dochvilného. Zavést ověřování platebních příkazů telefonem.",
         related_service_requests="TIS-47920", related_security_events="—", closed_at=ts(25, 11)[0],
         bec_type_final="CEO fraud", financial_loss_confirmed="Žádná", financial_loss_amount="0 Kč"),
    ratio=1.0, comm="Pochvala uživateli předána vedením.",
    extra_actions=[("Hromadné upozornění na CEO fraud (intranet)", "Komunikace", "Provedeno")],
    notes=["Hlavičky e-mailu: Reply-To na reditel.adk@gmail.example.", "Žádná platba neodešla."])

# 4 ─ BEC: dodavatel pneumatik mění účet
r, _ = ts(9, 13, 20)
soc("uib-bec-v2", "on_hold", "Pavel Louda", 9, 13,
    "BEC – Vendor Email Compromise · „PneuBus s.r.o.“ hlásí změnu čísla účtu · čeká se na banku",
    "T1657",
    dict(source_type="Hlášení zaměstnancem", reported_at=r, reporter_name="Vlasta Účetní",
         reporter_department="Účtárna", reporter_contact="vlasta.ucetni@adk.example, kl. 120",
         affected_user="vlasta.ucetni@adk.example", attachment_or_link="Ano – otevřena příloha",
         description_by_reporter="Dodavatel pneumatik poslal dopis, že mají nový účet v bance na Kajmanech. "
             "Prý kvůli lepšímu klimatu pro pneumatiky. Faktura 186 400 Kč už byla zadána do banky.",
         detection_tool="—", alert_id="—", alert_description="Hlášeno uživatelem."),
    dict(bec_action_taken="Ano – změna platebních", payment_stoppable="Možná", l2_initial_priority="P2"),
    ratio=0.6, comm="Banka kontaktována, čekáme na vyjádření k recall platby.",
    extra_actions=[("Recall platby u banky", "Finanční oddělení + banka", "Probíhá"),
                   ("Telefonické ověření u PneuBus s.r.o. na známém čísle", "Nákup", "Provedeno"),
                   ("Upozornit dodavatele na kompromitaci jejich schránky", "CSIRT", "Provedeno")],
    notes=["Doména pneubus-sro.example registrována před 4 dny – lookalike.", "Status: čekáme na banku (on hold)."])

# 5 ─ Uživatel ukradl počítač
r, _ = ts(17, 8, 0)
soc("uib-account-compromise-v2", "closed", "Petr Stoural", 17, 8,
    "Přihlášení z neznámé lokace · PC dispečinku zmizel · uživatel Otakar Nevečeřel si ho „půjčil“ domů i s monitorem",
    "T1078.002",
    dict(source_type="Automatizovaná detekce", reported_at=r, reporter_name="Entra ID Protection",
         reporter_department="—", reporter_contact="—", affected_user="otakar.nevecerel@adk.example",
         description_by_reporter="Při výslechu (pardon, pohovoru) uživatel uvedl: „Na home office jsem si vzal svůj počítač. "
             "Monitor taky, ten doma nemám. A klávesnici. A tu židli jsem vrátil.“",
         alert_timestamp=r, detection_tool="Entra ID Protection + Defender for Endpoint", alert_id="AAD-RISK-55120",
         affected_asset_auto="PC-DISP-02",
         alert_description="Device PC-DISP-02 (pevná stanice dispečinku) online z rezidenční IP v Unhošti. Inventura hlásí prázdný stůl."),
    dict(account_type="Běžný uživatel", session_active="Ne – aktivita ukončena", l2_initial_priority="P3"),
    dict(final_classification="Benign True Positive", impact_level="Nízká", impact_primary_service="Částečně nedostupné",
         impact_scope="Individuální", impact_duration="> 4 hodiny", impact_data="Žádný dopad na data",
         root_cause="Uživatel chybně pochopil pojem „home office“ jako „vezmi si kancelář domů“.",
         actions_taken="PC vráceno (bez židle, ta už byla vrácena dříve). Uživateli přidělen notebook. Ověřeno, že na PC nedošlo k úniku dat.",
         recommendations="Doplnit směrnici o home office o větu: „Nábytek a pevné stanice zůstávají v budově.“",
         related_service_requests="TIS-48003", related_security_events="AAD-RISK-55120", closed_at=ts(16, 10)[0],
         compromise_type_final="Nelze určit", account_type_final="Běžný uživatel", exfiltration_confirmed="Vyloučena"),
    ratio=1.0, comm="Personální oddělení informováno, uživatel dostal notebook a přednášku.",
    extra_actions=[("Fyzické vrácení PC-DISP-02 na dispečink", "Facility", "Provedeno"),
                   ("Přidělení notebooku NB-DISP-11", "Správce koncových stanic", "Provedeno")],
    assets=[("PC-DISP-02", "pc-disp-02.adk.example", "10.20.4.12", "Desktop", "Ano", "Dispečink – regulovaná služba, nyní zpět na místě")],
    notes=["GeoIP: Unhošť, rezidenční ISP.", "Uživatel kontaktován, vše vysvětlil s úsměvem."])

# 6 ─ Uživatel se zamotal do kabelu
r, _ = ts(12, 10, 45)
soc("uib-vpn-attack-v2", "closed", "Jakub Runda", 12, 10,
    "Podezření na brute-force VPN · ve skutečnosti se Honza Nesnídal zamotal do kabelu a vytrhl FW · reconnect storm",
    "T1110.001",
    dict(source_type="Automatizovaná detekce", reported_at=r, reporter_name="SIEM korelace",
         reporter_department="—", reporter_contact="—",
         description_by_reporter="Honza Nesnídal: „Nesl jsem si rohlík ze sklepa, něco se mi omotalo kolem nohy a pak zhasla serverovna.“",
         alert_timestamp=r, detection_tool="SIEM – UC-VPN-003 Brute-force", alert_id="SIEM-2026-10-30-1045",
         affected_asset_auto="FW-CENTRALA-01",
         alert_description="1 812 neúspěšných VPN přihlášení za 3 minuty od 96 uživatelů. FW-CENTRALA-01 heartbeat lost 10:41–10:44."),
    dict(attack_type_initial="Brute-force", access_confirmed="Ne – pouze", l2_initial_priority="P2"),
    dict(final_classification="False Positive", impact_level="Střední", impact_primary_service="Zcela nedostupné",
         impact_scope="Celoplošný", impact_duration="15 min", impact_data="Žádný dopad na data",
         root_cause="Fyzické odpojení napájecího kabelu firewallu nohou uživatele. Po obnovení se všichni VPN klienti naráz "
             "přihlašovali se starými tokeny → falešný brute-force.",
         actions_taken="Kabel zapojen, uživatel rozmotán, FW nabootován. Ověřeno, že všechny pokusy pocházejí ze známých klientů.",
         recommendations="Kabelové vedení ve sklepě uklidit do žlabu. Rohlíky skladovat jinde než v serverovně.",
         related_service_requests="TIS-48170", related_security_events="SIEM-2026-10-30-1045", closed_at=ts(12, 14)[0],
         attack_vector_final="Nelze určit", lateral_movement_confirmed="Ne", affected_systems_count="1 (FW) + 96 VPN klientů"),
    ratio=1.0, comm="Všem uživatelům rozeslána omluva za 3minutový výpadek VPN.",
    extra_actions=[("Instalace kabelového žlabu v serverovně", "Facility / Bohumil Kabelka", "Probíhá"),
                   ("Úprava UC-VPN-003: potlačit alert 10 min po restartu FW", "SIEM tým", "Provedeno")],
    assets=[("FW-CENTRALA-01", "fw-centrala-01.adk.example", "10.20.0.1", "Firewall", "Ano", "Napájení obnoveno, konfigurace beze změn")],
    notes=["Uptime FW 0 d 0 h 3 min – potvrzuje restart.", "Žádný pokus z externí IP mimo známé klienty."])

# 7 ─ Malware: kryptominer v crack jízdních řádů
r, _ = ts(6, 16, 30)
soc("uib-malware-v2", "in_progress", "Petr Stoural", 6, 16,
    "Kryptominer · „Jízdní řády PRO 2027 (crack)“ na PC dispečinku · uživatel: Antonín Dochvilný · ventilátor jak autobus",
    "T1496",
    dict(source_type="Hlášení zaměstnancem", reported_at=r, reporter_name="Antonín Dochvilný",
         reporter_department="Dispečink", reporter_contact="antonin.dochvilny@adk.example",
         affected_user="antonin.dochvilny@adk.example",
         description_by_reporter="Počítač hučí jako Karosa do kopce a jízdní řády se generují 40 minut. Prý je to novější verze, tak jsem čekal, že bude rychlejší.",
         alert_timestamp=ts(6, 16, 12)[0], detection_tool="Microsoft Defender for Endpoint", alert_id="MDE-ALERT-78105",
         affected_asset_auto="PC-DISP-05",
         alert_description="CPU 100 % po dobu 6 h, odchozí spojení na pool.xmr-mining.example:3333 – Coin miner behaviour."),
    dict(malware_type_initial="Kryptominer", isolation_required="Ano – izolace provedena", l2_initial_priority="P3"),
    ratio=0.55, comm="Uživatel informován, že legální licence je levnější než elektřina pro těžbu Monera.",
    extra_actions=[("Reimage PC-DISP-05", "Správce koncových stanic", "Čeká"),
                   ("Zablokovat instalaci SW bez admin práv (AppLocker)", "Správce AD", "Probíhá")],
    assets=[("PC-DISP-05", "pc-disp-05.adk.example", "10.20.4.15", "Desktop", "Ano", "Izolováno v MDE")],
    notes=["Instalátor stažen z jizdni-rady-zdarma.example.", "Persistence: naplánovaná úloha „AutobusUpdate“."])

# 8 ─ VPN: password spraying
r, _ = ts(1, 2, 10)
soc("uib-vpn-attack-v2", "open", "Jakub Runda", 1, 2,
    "Password spraying na SSL VPN · 2 300 pokusů ze 40 IP · zkoušené heslo „Autobus2026!“",
    "T1110.003",
    dict(source_type="Automatizovaná detekce", reported_at=r, reporter_name="SIEM korelace",
         reporter_department="—", reporter_contact="—", description_by_reporter="—",
         alert_timestamp=r, detection_tool="SIEM – UC-VPN-001 Password spraying", alert_id="SIEM-2026-11-10-0210",
         affected_asset_auto="FW-CENTRALA-01",
         alert_description="Pokusy o přihlášení na 412 účtů, heslo Autobus2026! a Kladno123. Zdrojové IP: rezidenční proxy, 12 zemí."),
    dict(attack_type_initial="Brute-force", access_confirmed="Podezření", l2_initial_priority="P2"),
    ratio=0.2, comm="",
    extra_actions=[("Ověřit 2 úspěšná přihlášení (účty bez MFA)", "Správce VPN", "Probíhá")],
    assets=[("FW-CENTRALA-01", "fw-centrala-01.adk.example", "10.20.0.1", "Firewall / VPN", "Ano", "SSL VPN portál")],
    notes=["Geo-blocking zatím vypnut kvůli řidičům na zájezdech v Chorvatsku."])

# 9 ─ MFA fatigue
r, _ = ts(0, 3, 12)
soc("uib-account-compromise-v2", "new", "Pavel Louda", 0, 3,
    "MFA fatigue · Otakar Nevečeřel schválil 47. push ve 3:12 ráno „aby to přestalo pípat“",
    "T1621",
    dict(source_type="Automatizovaná detekce", reported_at=r, reporter_name="Entra ID Protection",
         reporter_department="—", reporter_contact="—", affected_user="otakar.nevecerel@adk.example",
         description_by_reporter="(zatím nekontaktován – spí)",
         alert_timestamp=r, detection_tool="Entra ID Protection", alert_id="AAD-RISK-56901",
         alert_description="47 MFA push požadavků za 18 minut, poslední schválen. Přihlášení z IP 185.0.2.44 (NL)."),
    dict(account_type="Běžný uživatel", session_active="Ano – aktivní", l2_initial_priority="P2"),
    ratio=0.0)

# 10 ─ USB z autobusu
r, _ = ts(0, 9, 5)
soc("uib-malware-v2", "new", "Petr Stoural", 0, 9,
    "Nalezený USB disk „VÝPLATY 2026“ z linky 300 · zapojil Honza Nesnídal · „chtěl jsem jen najít majitele“",
    "T1204.002",
    dict(source_type="Hlášení zaměstnancem", reported_at=r, reporter_name="Honza Nesnídal",
         reporter_department="Dispečink", reporter_contact="honza.nesnidal@adk.example, kl. 214",
         affected_user="honza.nesnidal@adk.example",
         description_by_reporter="Řidič přinesl do ztrát a nálezů flashku s nápisem VÝPLATY 2026. Zapojil jsem ji, abych zjistil, čí je. "
             "Byl tam jen soubor vyplaty.xlsx.exe, ten se nějak sám otevřel.",
         alert_timestamp=ts(0, 8, 51)[0], detection_tool="Microsoft Defender for Endpoint", alert_id="MDE-ALERT-78440",
         affected_asset_auto="NB-DISP-07",
         alert_description="Execution of unsigned binary from removable media: vyplaty.xlsx.exe – blokováno ASR pravidlem."),
    dict(malware_type_initial="Nelze určit", isolation_required="Ano – izolace nařízena", l2_initial_priority="P3"),
    ratio=0.0)

# ═════════════════════════════════════════════════════════════════════════════
#  Datové zdroje – 10 průvodek
# ═════════════════════════════════════════════════════════════════════════════
def ds(status, days, hour, v, use_cases):
    def ex(data):
        sec(data, "use_cases")["rows"] = [
            dict(zip(["uc_id", "event_description", "mitre_tactic", "mitre_technique", "detection_method",
                      "severity", "playbook_ref"], u)) for u in use_cases]
    base = dict(data_owner_business="Ing. Miroslava Přísná (ředitelka provozu)", retention_approver="Mgr. Radim Paragraf (DPO)",
                legal_basis="ZKB 264/2025 Sb. (NIS2), vyhláška o bezpečnostních opatřeních, interní směrnice ADK-SEC-04",
                escalation_contact="soc@adk.example, +420 312 555 112")
    base.update(v)
    create("datasource", "datasource-v1", status, base, days, hour, ex)

ds("ingested", 44, 10, dict(
    source_name="Windows Server – doménové řadiče (DC01, DC02)", source_type="Windows Event Log / Active Directory",
    data_classification="Confidential", source_status="Active", garant="Karel Klíčník (správce AD)", record_owner="Petr Stoural",
    description="Bezpečnostní logy obou doménových řadičů. Kdo se kdy přihlásil, kdo si zamkl účet a kdo zase zapomněl heslo po dovolené.",
    fqdn_ip_list="dc01.adk.example – 10.20.0.10\ndc02.adk.example – 10.20.0.11", transfer_protocol="WEF → Winlogbeat → TLS 5044",
    data_format="JSON", normalization_parser="ECS – windows.security", source_timezone="Europe/Prague (UTC+1/+2)",
    transfer_auth="Mutual TLS (interní CA ADK)", ingest_endpoint="siem-ingest.adk.example:5044", typical_eps="180",
    typical_volume_per_day="9 GB", data_quality_score="9/10",
    notes="Pondělí ráno EPS ×5 – všichni si najednou vzpomenou na heslo.", related_tickets="TIS-45001",
    retention_online_months="12", retention_offline_months="24", required_capacity="3,3 TB / 12 měs.",
    monitoring_enabled="Ano", alert_on_outage="Ano", availability_sla="99,9 %"),
    [("UC-AD-001", "Opakované neúspěšné přihlášení (4625)", "Credential Access", "T1110", "Threshold", "Medium", "PB-ACC-01"),
     ("UC-AD-002", "Přidání do Domain Admins (4728)", "Privilege Escalation", "T1098", "Signature", "Critical", "PB-ACC-03"),
     ("UC-AD-003", "Kerberoasting (4769 RC4)", "Credential Access", "T1558.003", "Anomaly", "High", "PB-ACC-04")])

ds("ingested", 43, 14, dict(
    source_name="Windows Server – souborový server FS01", source_type="Windows Event Log / File auditing",
    data_classification="Confidential", source_status="Active", garant="Karel Klíčník (správce AD)", record_owner="Jakub Runda",
    description="Audit přístupu ke sdíleným složkám. Nejčtenější složka: \\\\fs01\\Jidelna\\Menu.",
    fqdn_ip_list="fs01.adk.example – 10.20.0.20", transfer_protocol="Winlogbeat → TLS 5044", data_format="JSON",
    normalization_parser="ECS – windows.security (4663, 5145)", source_timezone="Europe/Prague", transfer_auth="Mutual TLS",
    ingest_endpoint="siem-ingest.adk.example:5044", typical_eps="350", typical_volume_per_day="14 GB", data_quality_score="7/10",
    notes="Audit omezen na citlivé složky (Mzdy, Smlouvy). Složka Jídelna auditována na žádost vedoucího kuchyně.",
    related_tickets="TIS-45002", retention_online_months="6", retention_offline_months="18", required_capacity="2,5 TB",
    monitoring_enabled="Ano", alert_on_outage="Ano", availability_sla="99,5 %"),
    [("UC-FS-001", "Hromadné přejmenování souborů (ransomware)", "Impact", "T1486", "Threshold", "Critical", "PB-MAL-02"),
     ("UC-FS-002", "Přístup do složky Mzdy mimo pracovní dobu", "Collection", "T1039", "Correlation", "High", "PB-DATA-01")])

ds("accessible", 20, 9, dict(
    source_name="Windows Server – terminálový server dispečinku (RDS01)", source_type="Windows Event Log / RDS",
    data_classification="Internal", source_status="In Testing", garant="Bohumil Kabelka (správce infrastruktury)", record_owner="Pavel Louda",
    description="Přihlášení dispečerů na RDS farmu. Napojení v testu – pomalu, ale jistě (jak je u vlastníka průvodky zvykem).",
    fqdn_ip_list="rds01.adk.example – 10.20.0.30", transfer_protocol="Winlogbeat → TLS 5044", data_format="JSON",
    normalization_parser="ECS – windows.rdp", source_timezone="Europe/Prague", transfer_auth="Mutual TLS",
    ingest_endpoint="siem-ingest-test.adk.example:5044", typical_eps="40", typical_volume_per_day="1,5 GB", data_quality_score="—",
    notes="Čeká se na otevření portu na FW-CENTRALA-01 (viz UIB s kabelem – firewall měl jiné starosti).",
    related_tickets="TIS-48120", retention_online_months="6", retention_offline_months="12", required_capacity="270 GB",
    monitoring_enabled="Ne", alert_on_outage="Ne", availability_sla="99 %"),
    [("UC-RDP-001", "RDP přihlášení z nedispečerského účtu", "Lateral Movement", "T1021.001", "Correlation", "Medium", "PB-ACC-02")])

ds("identified", 8, 11, dict(
    source_name="macOS – MacBooky marketingu (Jamf Pro + Unified Log)", source_type="EDR / MDM",
    data_classification="Internal", source_status="Draft", garant="Jarmila Jízdní (marketing)", record_owner="Petr Stoural",
    description="Tři MacBooky marketingu. Marketing tvrdí, že „Macy viry nemají“. Průvodka vznikla, abychom to mohli doložit nebo vyvrátit.",
    fqdn_ip_list="MBP-MKT-01..03 (DHCP, VLAN 40)", transfer_protocol="Jamf Pro webhooks + Unified Log stream → HTTPS",
    data_format="JSON", normalization_parser="zatím žádný", source_timezone="Europe/Prague", transfer_auth="API token (Jamf)",
    ingest_endpoint="—", typical_eps="5", typical_volume_per_day="200 MB", data_quality_score="—",
    notes="Nutno vyjednat s marketingem. Doporučeno přijít s croissanty.", related_tickets="TIS-48390",
    retention_online_months="6", retention_offline_months="12", required_capacity="40 GB",
    monitoring_enabled="Ne", alert_on_outage="Ne", availability_sla="—"),
    [("UC-MAC-001", "Vypnutí Gatekeeper / SIP", "Defense Evasion", "T1553.001", "Signature", "High", "PB-MAL-01")])

ds("ingested", 41, 13, dict(
    source_name="Firewall – FortiGate centrála (FW-CENTRALA-01)", source_type="Next-Gen Firewall / SSL VPN",
    data_classification="Confidential", source_status="Active", garant="Bohumil Kabelka (správce infrastruktury)", record_owner="Jakub Runda",
    description="Hlavní firewall a SSL VPN centrály. Napájení dočasně „chráněno“ nápisem NEŠLAPAT NA KABEL.",
    fqdn_ip_list="fw-centrala-01.adk.example – 10.20.0.1 / 203.0.113.10", transfer_protocol="Syslog TLS 6514",
    data_format="CEF", normalization_parser="Fortinet FortiOS CEF", source_timezone="UTC", transfer_auth="TLS (server cert)",
    ingest_endpoint="siem-syslog.adk.example:6514", typical_eps="1 200", typical_volume_per_day="45 GB", data_quality_score="8/10",
    notes="Pozor: FW loguje v UTC, ostatní zdroje v Europe/Prague.", related_tickets="TIS-45010, TIS-48170",
    retention_online_months="12", retention_offline_months="24", required_capacity="16 TB",
    monitoring_enabled="Ano", alert_on_outage="Ano", availability_sla="99,95 %"),
    [("UC-VPN-001", "Password spraying na SSL VPN", "Credential Access", "T1110.003", "Threshold", "High", "PB-VPN-01"),
     ("UC-VPN-003", "Brute-force VPN (jeden účet)", "Credential Access", "T1110.001", "Threshold", "Medium", "PB-VPN-01"),
     ("UC-FW-010", "Spojení na známé C2 (TI feed)", "Command and Control", "T1071", "Threat Intel", "High", "PB-MAL-03")])

ds("accessible", 15, 8, dict(
    source_name="Firewall – vozovna Kladno-Kročehlavy (pfSense)", source_type="Firewall",
    data_classification="Internal", source_status="In Testing", garant="Bohumil Kabelka (správce infrastruktury)", record_owner="Pavel Louda",
    description="Firewall ve vozovně. Chrání dílnu, myčku autobusů a Wi-Fi pro řidiče na pauze.",
    fqdn_ip_list="fw-vozovna.adk.example – 10.30.0.1", transfer_protocol="Syslog UDP 514 (IPsec tunel)", data_format="Syslog",
    normalization_parser="pfSense filterlog", source_timezone="Europe/Prague", transfer_auth="žádná (v IPsec tunelu)",
    ingest_endpoint="siem-syslog.adk.example:514", typical_eps="60", typical_volume_per_day="2 GB", data_quality_score="5/10",
    notes="Myčka autobusů má IP adresu a posílá syslog „WASH CYCLE COMPLETE“ – parsuje se jako neznámá událost.",
    related_tickets="TIS-48201", retention_online_months="6", retention_offline_months="12", required_capacity="360 GB",
    monitoring_enabled="Ano", alert_on_outage="Ne", availability_sla="99 %"),
    [("UC-FW-020", "Port scan z Wi-Fi pro řidiče", "Discovery", "T1046", "Threshold", "Low", "PB-NET-01")])

ds("ingested", 40, 9, dict(
    source_name="Microsoft 365 – Entra ID sign-in a audit logy", source_type="Cloud IAM",
    data_classification="Confidential", source_status="Active", garant="Karel Klíčník (správce AD)", record_owner="Petr Stoural",
    description="Přihlášení do M365, risk events, změny MFA. Zdroj, který nám řekl, že pan Nevečeřel schvaluje MFA ve 3 ráno.",
    fqdn_ip_list="tenant adk.onmicrosoft.example", transfer_protocol="Event Hub → Azure connector (HTTPS)",
    data_format="JSON", normalization_parser="Azure AD SigninLogs / AuditLogs", source_timezone="UTC", transfer_auth="Service principal (OAuth2)",
    ingest_endpoint="SIEM Azure connector", typical_eps="25", typical_volume_per_day="1,2 GB", data_quality_score="9/10",
    notes="Licence E5 Security – risk events dostupné.", related_tickets="TIS-45020",
    retention_online_months="12", retention_offline_months="24", required_capacity="440 GB",
    monitoring_enabled="Ano", alert_on_outage="Ano", availability_sla="dle MS SLA 99,9 %"),
    [("UC-M365-001", "Impossible travel", "Initial Access", "T1078.004", "Anomaly", "High", "PB-ACC-01"),
     ("UC-M365-002", "MFA fatigue (≥10 push za 15 min)", "Credential Access", "T1621", "Threshold", "High", "PB-ACC-05"),
     ("UC-M365-003", "Nová inbox forwarding rule mimo doménu", "Collection", "T1114.003", "Signature", "High", "PB-BEC-01")])

ds("ingested", 39, 15, dict(
    source_name="Microsoft 365 – Exchange Online + Defender for Office 365", source_type="E-mail security",
    data_classification="Confidential", source_status="Active", garant="Karel Klíčník (správce AD)", record_owner="Jakub Runda",
    description="Pošta, SafeLinks, SafeAttachments, nahlášené zprávy. Hlavní zdroj elektrokoloběžek a faktur za naftu.",
    fqdn_ip_list="tenant adk.onmicrosoft.example", transfer_protocol="Microsoft 365 Defender API (HTTPS)", data_format="JSON",
    normalization_parser="M365 Defender – EmailEvents, UrlClickEvents", source_timezone="UTC", transfer_auth="Service principal (OAuth2)",
    ingest_endpoint="SIEM M365 Defender connector", typical_eps="15", typical_volume_per_day="800 MB", data_quality_score="8/10",
    notes="Tlačítko „Report Message“ nejčastěji používá pan Dochvilný – vždy jako první.", related_tickets="TIS-45021",
    retention_online_months="12", retention_offline_months="24", required_capacity="290 GB",
    monitoring_enabled="Ano", alert_on_outage="Ano", availability_sla="dle MS SLA"),
    [("UC-MAIL-001", "Uživatel klikl na phishing URL", "Initial Access", "T1566.002", "Signature", "Medium", "PB-PHI-01"),
     ("UC-MAIL-002", "Lookalike doména dodavatele", "Initial Access", "T1566", "Threat Intel", "High", "PB-BEC-02")])

ds("ingested", 37, 10, dict(
    source_name="Microsoft Defender for Endpoint – Windows stanice", source_type="EDR",
    data_classification="Confidential", source_status="Active", garant="Zdeněk Záloha (správce koncových stanic)", record_owner="Pavel Louda",
    description="EDR telemetrie ze 180 stanic a notebooků. Ví o kryptominerech v jízdních řádech i o flashkách z linky 300.",
    fqdn_ip_list="180 zařízení, onboarding přes Intune", transfer_protocol="M365 Defender API (HTTPS)", data_format="JSON",
    normalization_parser="M365 Defender – DeviceEvents, AlertInfo", source_timezone="UTC", transfer_auth="Service principal (OAuth2)",
    ingest_endpoint="SIEM M365 Defender connector", typical_eps="400", typical_volume_per_day="20 GB", data_quality_score="9/10",
    notes="PC-DISP-02 hlásil 3 dny polohu Unhošť – viz UIB „uživatel si půjčil počítač“.", related_tickets="TIS-45030",
    retention_online_months="6", retention_offline_months="12", required_capacity="3,6 TB",
    monitoring_enabled="Ano", alert_on_outage="Ano", availability_sla="dle MS SLA"),
    [("UC-EDR-001", "Spuštění binárky z USB", "Execution", "T1204.002", "Signature", "Medium", "PB-MAL-01"),
     ("UC-EDR-002", "Coin miner behaviour", "Impact", "T1496", "Signature", "Medium", "PB-MAL-04")])

ds("deprecated", 44, 16, dict(
    source_name="Firewall – Cisco PIX 515E v kotelně (legacy)", source_type="Firewall",
    data_classification="Internal", source_status="Deprecated", garant="Bohumil Kabelka (správce infrastruktury)", record_owner="Petr Stoural",
    description="Historický firewall z roku 2004. Nikdo neví, co chrání, ale všichni se bojí ho vypnout. Logy přestal posílat v roce 2019.",
    fqdn_ip_list="10.99.0.1 (asi)", transfer_protocol="Syslog UDP 514", data_format="Syslog", normalization_parser="—",
    source_timezone="neznámé (hodiny ukazují rok 1993)", transfer_auth="žádná", ingest_endpoint="—", typical_eps="0",
    typical_volume_per_day="0", data_quality_score="1/10",
    notes="Vyřazeno. Fyzická demontáž plánována, jakmile se najde klíč od kotelny.", related_tickets="TIS-30001",
    retention_online_months="0", retention_offline_months="0", required_capacity="0",
    monitoring_enabled="Ne", alert_on_outage="Ne", availability_sla="—"),
    [])

# ── spread created_at/updated_at into the past ───────────────────────────────
for collection, rid, dt, status, title in created:
    p = RECORDS_DIR / collection / f"{rid}.json"
    rec = json.loads(p.read_text())
    c = dt.replace(tzinfo=timezone.utc) - timedelta(hours=1)
    rec["created_at"] = c.isoformat().replace("+00:00", "Z")
    u = c + timedelta(hours=random.randint(1, 30)) if status != "new" else c + timedelta(minutes=20)
    rec["updated_at"] = min(u, datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    print(f"{collection:10} {rid:20} {status:12} {title[:80]}")
