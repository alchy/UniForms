#!/usr/bin/env python3
"""
Forms4SOC – startovací skript.
Spustí uvicorn server s aktivním .venv (pokud existuje).
Použití: python start.py [--port 8080] [--host 0.0.0.0] [--reload]
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent

def find_uvicorn() -> str:
    """Najde uvicorn – nejdříve ve .venv, pak v PATH."""
    for candidate in [
        BASE_DIR / ".venv" / "Scripts" / "uvicorn.exe",   # Windows venv
        BASE_DIR / ".venv" / "bin" / "uvicorn",           # Linux/macOS venv
    ]:
        if candidate.exists():
            return str(candidate)
    return "uvicorn"  # fallback – musí být v PATH

def find_python() -> str:
    """Najde python interpreter ve .venv nebo použije aktuální."""
    for candidate in [
        BASE_DIR / ".venv" / "Scripts" / "python.exe",
        BASE_DIR / ".venv" / "bin" / "python",
    ]:
        if candidate.exists():
            return str(candidate)
    return sys.executable

def main():
    parser = argparse.ArgumentParser(description="Forms4SOC server")
    parser.add_argument("--host", default="127.0.0.1", help="Adresa (výchozí: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port (výchozí: 8080)")
    parser.add_argument("--reload", action="store_true", help="Automatický reload při změně kódu")
    args = parser.parse_args()

    # Přepnout pracovní adresář na kořen projektu
    os.chdir(BASE_DIR)

    uvicorn = find_uvicorn()

    cmd = [
        uvicorn,
        "app.main:app",
        "--host", args.host,
        "--port", str(args.port),
        "--log-level", "info",
    ]
    if args.reload:
        cmd.append("--reload")

    print(f"Forms4SOC: http://{args.host}:{args.port}")
    print(f"API docs:  http://{args.host}:{args.port}/api/docs")
    print("Stop: Ctrl+C\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nServer zastaven.")
    except FileNotFoundError:
        print(f"Chyba: uvicorn nenalezen ({uvicorn}).")
        print("Nainstalujte závislosti: pip install -r requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    main()
