#!/usr/bin/env python3
"""
Stahne vsechny vendor JS/CSS knihovny pro lokalni pouziti (bez CDN).

Spust jednorazove pred prvnim spustenim aplikace:
    python scripts/download_vendors.py

Soubory jsou ulozeny do app/static/vendor/ a jsou servovany primo
webovym serverem aplikace. Adresar je v .gitignore - nesmí byt commitovan.

Tento skript nahrazuje scripts/download_ace.py.
"""
import sys
import urllib.request
from pathlib import Path

# Nastav UTF-8 vystup pro Windows konzoli
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VENDOR_DIR = Path(__file__).parent.parent / "app" / "static" / "vendor"

# User-Agent – nektere CDN (DataTables) blokuji python urllib bez nej
HEADERS = {"User-Agent": "Mozilla/5.0 Forms4SOC-vendor-downloader/1.0"}

# Struktura: "podadresar": [(url, lokalni_nazev), ...]
LIBRARIES = {
    "bootstrap/css": [
        (
            "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
            "bootstrap.min.css",
        ),
    ],
    "bootstrap/js": [
        (
            "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
            "bootstrap.bundle.min.js",
        ),
    ],
    "bootstrap-icons": [
        (
            "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
            "bootstrap-icons.min.css",
        ),
    ],
    "bootstrap-icons/fonts": [
        (
            "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2",
            "bootstrap-icons.woff2",
        ),
        (
            "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff",
            "bootstrap-icons.woff",
        ),
    ],
    "jquery": [
        (
            "https://code.jquery.com/jquery-3.7.1.min.js",
            "jquery.min.js",
        ),
    ],
    "datatables/css": [
        (
            "https://cdn.datatables.net/1.13.8/css/dataTables.bootstrap5.min.css",
            "dataTables.bootstrap5.min.css",
        ),
    ],
    "datatables/js": [
        (
            "https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js",
            "jquery.dataTables.min.js",
        ),
        (
            "https://cdn.datatables.net/1.13.8/js/dataTables.bootstrap5.min.js",
            "dataTables.bootstrap5.min.js",
        ),
    ],
    "ace": [
        (
            "https://cdnjs.cloudflare.com/ajax/libs/ace/1.32.9/ace.min.js",
            "ace.js",
        ),
        (
            "https://cdnjs.cloudflare.com/ajax/libs/ace/1.32.9/mode-json.min.js",
            "mode-json.js",
        ),
        (
            "https://cdnjs.cloudflare.com/ajax/libs/ace/1.32.9/mode-yaml.min.js",
            "mode-yaml.js",
        ),
        (
            "https://cdnjs.cloudflare.com/ajax/libs/ace/1.32.9/theme-tomorrow.min.js",
            "theme-tomorrow.js",
        ),
    ],
    "js-yaml": [
        (
            "https://cdnjs.cloudflare.com/ajax/libs/js-yaml/4.1.0/js-yaml.min.js",
            "js-yaml.min.js",
        ),
    ],
}


def fetch(url: str, target: Path) -> None:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as response:
        target.write_bytes(response.read())


def download() -> None:
    print(f"Vendor dir: {VENDOR_DIR}\n")
    total = sum(len(files) for files in LIBRARIES.values())
    downloaded = 0
    skipped = 0
    errors = 0

    for subdir, files in LIBRARIES.items():
        target_dir = VENDOR_DIR / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        for url, filename in files:
            target = target_dir / filename
            if target.exists():
                print(f"  [skip]  {subdir}/{filename}")
                skipped += 1
                continue
            print(f"  GET     {subdir}/{filename} ...")
            try:
                fetch(url, target)
                size_kb = target.stat().st_size // 1024
                print(f"          OK ({size_kb} KB)")
                downloaded += 1
            except Exception as exc:
                print(f"  [ERROR] {exc}")
                errors += 1

    print(f"\nDone: {downloaded} downloaded, {skipped} skipped, {errors} errors (total {total}).")
    if errors == 0:
        print("All vendor libraries ready in app/static/vendor/")
    else:
        print("Some downloads failed – check errors above and re-run.")


if __name__ == "__main__":
    download()
