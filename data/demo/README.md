# Ukázková data (demo)

Snímek fiktivních záznamů pro předvedení UniForms. Každý adresář odpovídá jedné kolekci.

| Kolekce | Záznamů | Obsah |
|---------|--------:|-------|
| `soc` | 10 | Bezpečnostní incidenty fiktivní firmy *Autobusová doprava Kladno* (phishing, BEC, VPN, malware, MFA fatigue …) |
| `datasource` | 10 | Průvodky datových zdrojů – Windows servery, macOS, firewally, Microsoft 365, Defender |
| `zoo` | 5 | Zoo Evidence – pštros Ulrich, paní Ulrychová, dvě pštrosíčata a tučňák Olda |

Všechny osoby, firmy a domény (`adk.example`) jsou smyšlené.

## Nahrání

**Zkopírováním** (rychlé, zachová původní ID a data):

```bash
for c in soc datasource zoo; do mkdir -p data/records/$c && cp data/demo/records/$c/*.json data/records/$c/; done
```

**Přes API** (vygeneruje nové záznamy, ověří šablony):

```bash
UNIFORMS_URL=http://127.0.0.1:8080 UNIFORMS_USER=admin python scripts/seed_demo_adk.py <heslo>
UNIFORMS_URL=http://127.0.0.1:8080 UNIFORMS_USER=admin python scripts/seed_demo_zoo.py <heslo>
```

Adresář `data/records/` je v `.gitignore` (provozní data), proto jsou ukázky tady.
