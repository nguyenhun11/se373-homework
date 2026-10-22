"""Tool registry: one place that defines name, description, args and handler.

The system prompt is generated from this registry, so adding a tool here is
enough for the agent to discover and use it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import db
import memory_store


@dataclass
class Tool:
    name: str
    description: str
    args: dict[str, str]  # arg name -> description
    handler: Callable[..., str]


def _registry(session_id: str) -> dict[str, Tool]:
    tools = [
        Tool("list_tables", "List the tables in the Chợ Sen database.", {}, db.list_tables),
        Tool("describe_table", "Show the columns (CREATE TABLE) and 3 sample rows of a table.",
             {"table": "table name"}, db.describe_table),
        Tool("run_sql", f"Run ONE read-only SQLite query (SELECT/WITH). Returns at most {db.MAX_ROWS} rows. "
             "On an error, read the message, fix the query and try again.",
             {"sql": "SQLite query"}, db.run_sql),
        Tool("remember", "Save or change a durable project convention. Reuse an existing key to replace it.",
             {"key": "snake_case key", "value": "the convention", "reason": "why"},
             lambda key, value, reason="": memory_store.remember(key, value, reason, session_id)),
        Tool("forget", "Retire a convention with no replacement.",
             {"key": "existing key", "reason": "why"},
             lambda key, reason="": memory_store.forget(key, reason, session_id)),
        Tool("history", "Show past values of a convention.", {"key": "key"},
             lambda key: json.dumps(memory_store.history(key), ensure_ascii=False)),
    ]
    return {t.name: t for t in tools}


class Toolbox:
    def __init__(self, session_id: str):
        self.tools = _registry(session_id)

    def describe(self) -> str:
        lines = []
        for t in self.tools.values():
            args = ", ".join(f'"{k}": <{v}>' for k, v in t.args.items())
            lines.append(f"- {t.name}({{{args}}}): {t.description}")
        return "\n".join(lines)

    def call(self, name: str, args: dict) -> tuple[str, bool]:
        """Returns (observation, is_error). Errors are fed back to the model, never raised."""
        tool = self.tools.get(name)
        if tool is None:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self.tools)}", True
        if not isinstance(args, dict):
            return "ERROR: args must be a JSON object.", True
        missing = [a for a in tool.args if a not in args and a != "reason"]
        if missing:
            return f"ERROR: missing argument(s) {missing} for '{name}'.", True
        try:
            result = tool.handler(**{k: v for k, v in args.items() if k in tool.args})
        except Exception as e:  # a crashing tool must not crash the loop
            return f"ERROR: {type(e).__name__}: {e}", True
        return result, result.startswith(("ERROR", "SQL ERROR"))
