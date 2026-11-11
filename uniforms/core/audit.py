"""Audit trail: JSONL, one line = one event.

Modelled on access-manager's audit (github.com/alchy/access-manager):

- daily files ``{audit_dir}/YYYY-MM-DD.jsonl`` – retention is just deleting
  old files, reading a date range is cheap;
- append is a single ``os.write`` with ``O_APPEND``, so concurrent lines never
  interleave even without a lock;
- directory 0700, files 0600;
- secrets (passwords, tokens, cookies) are NEVER logged – callers pass only
  identifiers (username, collection, record id …);
- reading tolerates a broken / hand-edited line (it is skipped) and splits on
  ``\\n`` only (``str.splitlines`` would also split on U+2028 etc. that
  ``ensure_ascii=False`` leaves raw in values, and silently hide the event).

Event fields (an unknown value is omitted, never written as empty):

    t        ISO-8601 UTC timestamp
    kind     "auth" (login/logout) | "write" (any state-changing API call)
    op       operation – the API endpoint name (login, update_record, …)
    actor    who did it – "user:<name>" (from the session)
    subject  whom it concerned when it is not the actor (failed login name)
    origin   client IP address (as seen through the reverse proxy)
    outcome  ok | denied (401/403/423) | rejected (other 4xx) | error (5xx)
    status   HTTP status code
    error    short error detail for non-ok outcomes
    + target identifiers from the URL (collection_id, record_id, template_id,
      username) and op-specific extras (e.g. status_from / status_to)
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DIR_MODE = 0o700
FILE_MODE = 0o600


def append_event(audit_dir: Path | str, event: dict, retention_days: int) -> None:
    """Append one event; never raises (auditing must not break the request)."""
    try:
        adresar = Path(audit_dir)
        created = not adresar.exists()
        adresar.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        if created:
            os.chmod(adresar, DIR_MODE)  # mkdir mode is subject to umask
        now = datetime.now(timezone.utc)
        event = {"t": now.isoformat(timespec="seconds"), **event}
        event = {k: v for k, v in event.items() if v is not None and v != ""}
        target = adresar / f"{now:%Y-%m-%d}.jsonl"
        if not target.exists():
            _prune(adresar, retention_days)
        line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, FILE_MODE)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception as exc:  # pragma: no cover – disk full, permissions …
        logger.error("Cannot write audit event %s: %s", event.get("op"), exc)


def _prune(adresar: Path, retention_days: int) -> None:
    """Delete daily files older than the retention. Runs once per new day file."""
    if retention_days <= 0:
        return
    limit = time.time() - retention_days * 86400
    for f in adresar.glob("*.jsonl"):
        try:
            day = datetime.strptime(f.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue  # not ours
        if day.timestamp() < limit:
            f.unlink(missing_ok=True)


def _lines(f: Path) -> list[str]:
    return f.read_text(encoding="utf-8").split("\n")


def matches(event: dict, *, who: Optional[str] = None, kind: Optional[str] = None,
            outcome: Optional[str] = None, collection_id: Optional[str] = None,
            text: Optional[str] = None) -> bool:
    """Filter used by read_events (and the admin console).

    ``who`` matches actor OR subject as a case-insensitive substring – the admin
    filters by what the table shows ("demo" finds "user:demo"). ``text`` is a
    free-text substring over the whole serialized event.
    """
    if who and not any(who.lower() in (event.get(k) or "").lower() for k in ("actor", "subject")):
        return False
    if kind and event.get("kind") != kind:
        return False
    if outcome and event.get("outcome") != outcome:
        return False
    if collection_id and event.get("collection_id") != collection_id:
        return False
    if text and text.lower() not in json.dumps(event, ensure_ascii=False).lower():
        return False
    return True


def read_events(audit_dir: Path | str, day_from: Optional[str] = None,
                day_to: Optional[str] = None, *, limit: int = 1000, **filters) -> list[dict]:
    """Events in [day_from, day_to] (``YYYY-MM-DD``, inclusive), NEWEST FIRST.

    Reads from the newest day backwards and stops once ``limit`` matches are
    collected, so the common case (recent events) touches one or two files.
    """
    adresar = Path(audit_dir)
    if not adresar.is_dir():
        return []
    out: list[dict] = []
    for f in sorted(adresar.glob("*.jsonl"), reverse=True):
        day = f.stem
        if day_to and day > day_to:
            continue
        if day_from and day < day_from:
            break
        for line in reversed(_lines(f)):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # one bad line must not break the console
            if matches(event, **filters):
                out.append(event)
                if len(out) >= limit:
                    return out
    return out


def days_available(audit_dir: Path | str) -> list[str]:
    adresar = Path(audit_dir)
    if not adresar.is_dir():
        return []
    return sorted((f.stem for f in adresar.glob("*.jsonl")), reverse=True)


def principal(username: Optional[str]) -> Optional[str]:
    return f"user:{username}" if username else None
