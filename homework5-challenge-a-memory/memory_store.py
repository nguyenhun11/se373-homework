"""Persistent memory store for project conventions.

Design (see slides 10-12, 16):
- memory/memory.json is the source of truth. Each record is one convention,
  identified by a stable `key` (e.g. `sql_dialect`).
- Writing a key that already exists does NOT append a second "active" rule.
  The old record is marked `superseded` with the time, session and reason,
  and the new record points back to it. History is kept; only active
  records are injected into the context.
- memory/MEMORY.md is a human-readable view, regenerated on every write.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

MEMORY_DIR = Path(os.environ.get("AGENT_MEMORY_DIR", Path(__file__).parent / "memory"))
STORE_PATH = MEMORY_DIR / "memory.json"
VIEW_PATH = MEMORY_DIR / "MEMORY.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> list[dict]:
    if not STORE_PATH.exists():
        return []
    return json.loads(STORE_PATH.read_text(encoding="utf-8"))


def _save(records: list[dict]) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)  # atomic write: a crash never leaves half a file
    _render_view(records)


def _render_view(records: list[dict]) -> None:
    lines = ["# Project memory (generated from memory.json — do not edit)", "", "## Active"]
    for r in records:
        if r["status"] == "active":
            lines.append(f"- **{r['key']}**: {r['value']}  _(since {r['created_at']}, session {r['source_session']})_")
    lines += ["", "## Superseded (history)"]
    for r in records:
        if r["status"] == "superseded":
            lines.append(
                f"- ~~{r['key']}: {r['value']}~~ → replaced by #{r['superseded_by']} "
                f"at {r['superseded_at']} (reason: {r.get('superseded_reason') or '-'})"
            )
    VIEW_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def active() -> list[dict]:
    return [r for r in _load() if r["status"] == "active"]


def remember(key: str, value: str, reason: str, session_id: str) -> str:
    """Upsert a convention. An existing active value for the key is superseded."""
    key = key.strip().lower().replace(" ", "_")
    records = _load()
    current = next((r for r in records if r["key"] == key and r["status"] == "active"), None)
    if current and current["value"].strip() == value.strip():
        return f"No change: '{key}' is already '{value}'."

    new_id = max((r["id"] for r in records), default=0) + 1
    if current:
        current.update(
            status="superseded",
            superseded_by=new_id,
            superseded_at=_now(),
            superseded_reason=reason,
        )
    records.append(
        {
            "id": new_id,
            "key": key,
            "value": value,
            "status": "active",
            "created_at": _now(),
            "source_session": session_id,
            "reason": reason,
            "supersedes": current["id"] if current else None,
        }
    )
    _save(records)
    if current:
        return f"Updated '{key}': '{current['value']}' -> '{value}' (old record #{current['id']} marked superseded)."
    return f"Saved new convention '{key}' = '{value}'."


def forget(key: str, reason: str, session_id: str) -> str:
    """Retire a convention without a replacement (kept in history)."""
    records = _load()
    current = next((r for r in records if r["key"] == key and r["status"] == "active"), None)
    if not current:
        return f"No active convention '{key}'."
    current.update(status="superseded", superseded_by=None, superseded_at=_now(),
                   superseded_reason=f"forgotten in {session_id}: {reason}")
    _save(records)
    return f"Retired '{key}'."


def history(key: str) -> list[dict]:
    return [r for r in _load() if r["key"] == key]


def context_block() -> str:
    """The exact text injected into the system prompt at session start."""
    rules = active()
    if not rules:
        return "<project_memory>\n(no conventions saved yet)\n</project_memory>"
    body = "\n".join(f"- {r['key']}: {r['value']}  (updated {r['created_at']})" for r in rules)
    return f"<project_memory>\n{body}\n</project_memory>"


def dump_all() -> str:
    return json.dumps(_load(), ensure_ascii=False, indent=2)
