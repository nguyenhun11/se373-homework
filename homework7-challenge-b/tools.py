"""Tool registry: one place that defines name, description, args and handler.

The system prompt is generated from this registry, so adding a tool here is
enough for the agent to discover and use it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import codemode
import db
import logs
import memory_store


@dataclass
class Tool:
    name: str
    description: str
    args: dict[str, str]  # arg name -> description
    handler: Callable[..., str]


def _registry(session_id: str, mode: str) -> dict[str, Tool]:
    """mode="native": the model calls the log tools itself and sees their raw output.
    mode="code": the log tools are only reachable from programs sent to run_code."""
    log_tools = [
        Tool("list_logs", "List the service log files (name, line count, size).", {}, logs.list_logs),
        Tool("read_log", f"Read raw lines of one log file, at most {logs.MAX_READ} lines per call.",
             {"file": "log file name", "offset": "first line, 1-based (optional)",
              "limit": f"number of lines, max {logs.MAX_READ} (optional)"}, logs.read_log),
        Tool("grep_log", f"Regex search in one log file, or all files if file is empty. "
             f"Returns at most {logs.MAX_GREP} matching lines.",
             {"pattern": "Python regex", "file": "log file name, or empty for all files (optional)"}, logs.grep_log),
    ] if mode == "native" else [
        Tool("list_logs", "List the service log files (name, line count, size).", {}, logs.list_logs),
        Tool("run_code", "Run a Python program in a separate confined runtime and return ONLY what it prints "
             f"(max {codemode.MAX_OUTPUT} chars). Use it for every log analysis: loop over files, filter, "
             "count and join with SQL inside the program, then print only the final, aggregated findings "
             "(counts, top-N, a few example lines) — never raw logs.\n" + codemode.SDK_DOC,
             {"code": "Python source"}, codemode.run_code),
    ]
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
        *log_tools,
    ]
    return {t.name: t for t in tools}


class Toolbox:
    def __init__(self, session_id: str, mode: str = "native"):
        self.tools = _registry(session_id, mode)

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
        missing = [a for a, desc in tool.args.items()
                   if a not in args and a != "reason" and "(optional)" not in desc]
        if missing:
            return f"ERROR: missing argument(s) {missing} for '{name}'.", True
        try:
            result = tool.handler(**{k: v for k, v in args.items() if k in tool.args})
        except Exception as e:  # a crashing tool must not crash the loop
            return f"ERROR: {type(e).__name__}: {e}", True
        return result, result.startswith(("ERROR", "SQL ERROR"))
