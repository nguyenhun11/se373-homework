"""Code Mode runtime (Challenge B2).

The model sends a Python program through the `run_code` tool. The program runs in a
SEPARATE PROCESS, calls the same data tools through the `tools` SDK, loops and
aggregates there, and only what it prints comes back to the model.

Where does the code run?
- `python3 -I` child process (isolated mode: no user site-packages, no script dir on sys.path)
- inside bubblewrap when available: read-only view of /usr and of this project's data and
  modules, private /tmp, no network, no other processes (--unshare-all), empty environment
  (so no API keys can leak), killed with the parent
- resource limits: CPU time, memory, file size; wall-clock timeout
- SQL stays read-only (db.py opens SQLite with mode=ro)
This is a confined runtime, not a hardened security sandbox: production would add a
container/VM, per-tool permission checks and audit logs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
TIMEOUT_S = 20
MAX_OUTPUT = 2000  # chars of stdout returned to the model

SDK_DOC = """Inside the program, a ready-made `tools` object is available (no import needed):
  tools.list_logs() -> list[str]                    log file names, e.g. "payment-service-2025-03-14.log"
  tools.read_log(file) -> list[str]                 ALL lines of one file (no limit)
  tools.grep(pattern, file=None) -> list[(file, line_no, line)]   regex search, all files if file is None
  tools.parse(line) -> dict | None                  {"date","time","level","service", plus key=value fields such as
                                                    "code","order_id","gateway","msg"}; None for nginx access lines
  tools.run_sql(sql) -> list[dict]                  read-only SQLite (SELECT/WITH), tables: orders, order_items,
                                                    products, customers
Log line format: '2025-03-14 20:05:12.345 ERROR [payment-service] req=r-1a2b order_id=12 gateway=vnpay code=X msg="..."'
nginx lines: '<ip> - - [14/Mar/2025:20:05:12 +0700] "POST /api/payment/charge HTTP/1.1" 504 <bytes> <secs> req=r-..'
Standard library modules (re, collections, json, datetime, ...) can be imported."""


def _bwrap_prefix() -> list[str]:
    if not shutil.which("bwrap"):
        return []
    args = ["bwrap", "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
            "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", str(ROOT / "data"), str(ROOT / "data"),
            "--unshare-all", "--die-with-parent", "--clearenv", "--chdir", "/tmp"]
    for module in ("codemode.py", "db.py", "logs.py"):
        args += ["--ro-bind", str(ROOT / module), str(ROOT / module)]
    return args


def _limits() -> None:  # runs in the child before exec
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_S, TIMEOUT_S))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))       # 1 GB memory
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))    # 1 MB per written file


def run_code(code: str) -> str:
    """Tool handler: execute the program, return only its (capped) stdout or the error."""
    prefix = _bwrap_prefix()
    cmd = prefix + ["/usr/bin/python3" if prefix else sys.executable, "-I", str(ROOT / "codemode.py"), "--child"]
    try:
        out = subprocess.run(cmd, input=code, capture_output=True, text=True, timeout=TIMEOUT_S, cwd="/tmp",
                             preexec_fn=_limits, env=None if prefix else {"PATH": "/usr/bin:/bin"})
    except subprocess.TimeoutExpired:
        return f"ERROR: program exceeded the {TIMEOUT_S}s time limit. Make it faster (e.g. use tools.grep)."
    text = out.stdout.strip()
    if out.returncode != 0:
        err = out.stderr.strip().splitlines()
        return "ERROR: program failed:\n" + "\n".join(err[-8:]) + (f"\nstdout before the error:\n{text[:500]}" if text else "")
    if not text:
        return "ERROR: the program printed nothing. print() the final result."
    if len(text) > MAX_OUTPUT:
        return (text[:MAX_OUTPUT] + f"\n... (output truncated at {MAX_OUTPUT} chars — "
                "print only aggregated findings, not raw lines)")
    return text


# ---------------------------------------------------------------- child side
class _SDK:
    """The `tools` object a program sees. Same data tools as native mode, without the caps."""

    def __init__(self):
        import db
        import logs
        self._db, self._logs = db, logs

    def list_logs(self):
        return self._logs.names()

    def read_log(self, file):
        return self._logs.lines(file)

    def grep(self, pattern, file=None):
        return self._logs.grep(pattern, file)

    def parse(self, line):
        return self._logs.parse(line)

    def run_sql(self, sql):
        return self._db.query(sql)


def _child() -> None:
    sys.path.insert(0, str(ROOT))  # -I removed the script dir from sys.path; add only our modules' dir
    code = sys.stdin.read()
    exec(compile(code, "<run_code>", "exec"), {"tools": _SDK(), "__name__": "__main__"})


if __name__ == "__main__" and sys.argv[1:] == ["--child"]:
    _child()
