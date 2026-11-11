#!/usr/bin/env python3
"""Demo data – Zoo Evidence: ostriches (Ulrich & family) and Olda the penguin.

Usage:
    UNIFORMS_URL=http://127.0.0.1:8080 UNIFORMS_USER=admin python scripts/seed_demo_zoo.py <password>

Creates records through the REST API (same structure as records made in the UI), then
back-dates created_at directly in data/records/ so the dashboard looks lived-in.
Requires the target collections/templates to exist (they ship in data/collections, data/schemas).
"""
import os
import json, sys, urllib.request, http.cookiejar
from datetime import datetime, timedelta, timezone
from pathlib import Path
B = os.environ.get("UNIFORMS_URL", "http://127.0.0.1:8080").rstrip("/")
RD = Path(__file__).resolve().parents[1] / "data" / "records" / "zoo"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def api(m, p, b=None):
    r = urllib.request.Request(B + p, method=m, data=json.dumps(b).encode() if b is not None else None,
                               headers={"Content-Type": "application/json"})
    with op.open(r) as x: t = x.read(); return json.loads(t) if t else None
api("POST", "/api/v1/auth/login", {"username": os.environ.get("UNIFORMS_USER", "admin"), "password": sys.argv[1]})

def walk(ss):
    for s in ss:
        yield s; yield from walk((s.get("sections") or []) + (s.get("subsections") or []))

def animal(tpl, status, days_ago, values, feeding, vet, diary, checks_done):
    rec = api("POST", "/api/v1/records/zoo/", {"template_id": tpl}); d = rec["data"]; left = dict(values)
    for s in walk(d["sections"]):
        for f in s.get("fields") or []:
            if f["key"] in left:
                v = left.pop(f["key"])
                if f.get("type") == "select":
                    m = [o for o in f["options"] if o == v] or [o for o in f["options"] if o.startswith(v)]
                    assert len(m) == 1, (f["key"], v, f["options"]); v = m[0]
                f["value"] = v
        if s["id"] == "feeding": s["rows"] = [dict(zip(["time", "food", "amount", "note"], r)) for r in feeding]
        if s["id"] == "vet_care": s["rows"] = [dict(zip(["date", "procedure", "vet", "result"], r)) for r in vet]
        if s["id"] == "diary": s["rows"] = [dict(zip(["date", "entry"], r)) for r in diary]
        if s["type"] == "checklist":
            for i, st in enumerate(x for g in s["step_groups"] for x in g["steps"]): st["done"] = i < checks_done
    assert not left, left
    api("PATCH", f"/api/v1/records/zoo/{rec['record_id']}", {"status": status, "data": d})
    p = RD / f"{rec['record_id']}.json"; j = json.loads(p.read_text())
    c = datetime.now(timezone.utc) - timedelta(days=days_ago)
    j["created_at"] = c.isoformat().replace("+00:00", "Z"); p.write_text(json.dumps(j, ensure_ascii=False, indent=2))
    print(rec["record_id"], status, values["animal_name"])

MARIE, BOHOUS = "Marie Krmivová", "Bohouš Šupina"

animal("zoo-pstros-v1", "exhibit", 400, dict(
    animal_name="Ulrich", record_owner=MARIE, sex="Samec", born_at="2019-04-12T06:30", origin="Přesun z jiné zoo",
    chip_id="RING-CZ-0107", weight_kg=148, enclosure="Savana B", father="neznámý (prý šlechtic)", mother="neznámá",
    distinguishing_marks="Černé peří s noblesou, jedno pírko na hlavě vždy trčí doleva.",
    temperament="Panovačná", visitor_rating=9,
    habits="Každé ráno v 7:00 obchází výběh jako starosta. Nesnáší deštníky a pana ředitele.",
    category="Pštros (dospělý samec)", height_cm=255, top_speed_kmh=68, head_in_sand="Ne – to je mýtus",
    mating_dance="Porota: 9/10. Paní Ulrychová: „ujde to“."),
    [("07:00", "Granule pro běžce", "2 kg", "Podávat až po ranní obchůzce"), ("15:00", "Zelenina + vojtěška", "3 kg", "Mrkev krájet, celou neuznává")],
    [("2026-03-14", "Preventivní prohlídka", "MVDr. Tlapka", "Zdravé"), ("2026-09-02", "Odčervení", "MVDr. Tlapka", "Nespolupracovalo")],
    [("2026-11-02", "Kopnutím otevřel kbelík s mrkví. Výkonnostně zaznamenáno."), ("2026-11-09", "Hlídá hnízdo, ošetřovatelku pustil až na třetí pokus.")], 5)

animal("zoo-pstros-v1", "breeding", 400, dict(
    animal_name="paní Ulrychová", record_owner=MARIE, sex="Samice", born_at="2020-05-03T08:00", origin="Přesun z jiné zoo",
    chip_id="RING-CZ-0108", weight_kg=112, enclosure="Savana B – hnízdiště", father="neznámý", mother="neznámá",
    distinguishing_marks="Šedohnědé peří, přísný pohled, výrazné řasy.",
    temperament="Klidná", visitor_rating=8,
    habits="Trvá na tom, že je „paní Ulrychová“, ne „Ulrichová“. Pravopis manžela neřeší.",
    category="Pštrosice (dospělá samice)", height_cm=190, top_speed_kmh=61, head_in_sand="Jen když přijde inventura", eggs_laid=14),
    [("07:30", "Granule pro běžce + vápník", "1,8 kg", "V době snášky přidat vápník"), ("15:00", "Zelenina + vojtěška", "2,5 kg", "")],
    [("2026-09-20", "Kontrola po snášce", "MVDr. Tlapka", "Zdravé")],
    [("2026-10-10", "Snesla 14. vejce, s Ulrichem se střídá v sezení."), ("2026-10-12", "Vylíhla se dvě mláďata. Je pyšná.")], 5)

for name, cat_note, days, weight, height, temp, habits, rating in [
    ("Ulrychov Antonín Pavlovič", "", 30, 6.5, 62, "Zvídavá",
     "Vylíhl se jako první a od té doby se chová jako nejstarší sourozenec. Zkouší dupat jako táta.", 10),
    ("Ulrychovová Jana Krátká", "", 29, 4.1, 48, "Uražená",
     "Nejmenší z hnízda, ale nejhlasitější. Urazí se, když jí někdo říká Krátká. Jinak se jmenovat nechce.", 10)]:
    animal("zoo-pstros-v1", "breeding", days, dict(
        animal_name=name, record_owner=MARIE, sex="Samec" if "Antonín" in name else "Samice",
        born_at=(datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M"), origin="Odchov v naší zoo",
        chip_id="RING-CZ-0" + ("201" if "Antonín" in name else "202"), weight_kg=weight, enclosure="Savana B – školka",
        father="Ulrich", mother="paní Ulrychová",
        distinguishing_marks="Pruhované prachové peří." + (" Ocas jako štětka." if "Antonín" in name else " Nejkratší krk v rodině."),
        temperament=temp, visitor_rating=rating, habits=habits,
        category="Pštrosíče (mládě)", height_cm=height, top_speed_kmh=None, head_in_sand="Nevyzkoušeno"),
        [("07:00", "Starter pro mláďata", "300 g", "Rozdělit do 3 dávek"), ("12:00", "Starter + drobná zelenina", "200 g", ""),
         ("17:00", "Starter", "200 g", "")],
        [((datetime.now() - timedelta(days=days - 2)).strftime("%Y-%m-%d"), "Prohlídka po vylíhnutí", "MVDr. Tlapka", "Zdravé")],
        [((datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
          "Vážení: přibral(a) 300 g. Sourozenec to komentoval pípáním.")], 3)

animal("zoo-tucnak-v1", "exhibit", 365, dict(
    animal_name="Olda", record_owner=BOHOUS, sex="Samec", born_at="2017-12-24T10:00", origin="Odchov v naší zoo",
    chip_id="RING-CZ-0033", weight_kg=4.4, enclosure="Pavilon Humboldt – bazén 1", father="Bedřich", mother="Květa",
    distinguishing_marks="Na hrudi tečka ve tvaru Česka (při troše fantazie).",
    temperament="Klidná", visitor_rating=10,
    habits="Narozen na Štědrý den, proto čeká dárek každý den. Před krmením stojí v řadě vždy první, i když tam nikdo jiný není.",
    category="Tučňák (dospělý)", favourite_fish="Šprot", dive_record_m=21, waddle_style="Kolébání s nadhledem",
    wearing_tuxedo="Vždy (jinak to nejde)"),
    [("09:00", "Šprot", "250 g", "Podávat z ruky, z kbelíku se uráží"), ("16:00", "Sleď + vitamíny", "200 g", "Vitamín schovat do ryby")],
    [("2026-06-11", "Kontrola peří po přepeřování", "MVDr. Tlapka", "Zdravé")],
    [("2026-11-05", "Pozoroval návštěvníky 40 minut bez mrknutí. Návštěvníci odešli první."),
     ("2026-11-10", "Odmítl huňáčka. Trvá na šprotech.")], 5)
