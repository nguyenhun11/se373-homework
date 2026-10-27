"""Fake "Chợ Sen" service logs (Challenge B) and the log tools.

`python3 logs.py`          rebuilds data/logs/ (deterministic: same seed -> same files)
`python3 logs.py --truth`  prints the ground-truth answers, computed by parsing the files

Planted incident: on 2025-03-14 at 19:58 a deploy lowers the VNPay gateway timeout
from 3000ms to 300ms. Most VNPay charges then time out (PAY_GATEWAY_TIMEOUT) until
the rollback at 21:04. Red herring: an inventory STOCK_SYNC_LAG burst around 20:30.

Two views of the same data:
- native tools (read_log, grep_log) return capped raw text -> it goes into the context
- the plain functions (lines, grep) are what Code Mode scripts call: no cap, data
  stays in the runtime and only the script's printed result reaches the model
"""

from __future__ import annotations

import random
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path(__file__).parent / "data" / "logs"
DAYS = ["2025-03-12", "2025-03-13", "2025-03-14", "2025-03-15", "2025-03-16"]
INCIDENT_DAY = "2025-03-14"
INCIDENT_START, INCIDENT_END = "19:58:03", "21:04:40"
MAX_READ = 200    # lines per read_log call (native)
MAX_GREP = 100    # matching lines per grep_log call (native)

LINE_RE = re.compile(r"^(\S+) (\S+) (\w+) +\[([\w-]+)\] (.*)$")


# ---------------------------------------------------------------- generator
def build(seed: int = 3730) -> None:
    rng = random.Random(seed)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for old in LOG_DIR.glob("*.log"):
        old.unlink()
    for day in DAYS:
        files: dict[str, list[tuple[str, str]]] = {s: [] for s in
                                                   ("order-service", "payment-service", "inventory-service", "nginx")}
        _build_day(rng, day, files)
        for service, rows in files.items():
            rows.sort(key=lambda r: r[0])
            (LOG_DIR / f"{service}-{day}.log").write_text("\n".join(r[1] for r in rows) + "\n", encoding="utf-8")


def _ts(day: str, seconds: float) -> datetime:
    return datetime.fromisoformat(day) + timedelta(seconds=seconds)


def _app(t: datetime, level: str, service: str, msg: str) -> tuple[str, str]:
    stamp = t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d}"
    return stamp, f"{stamp} {level:<5} [{service}] {msg}"


def _nginx(t: datetime, rng: random.Random, method: str, path: str, status: int, req: str) -> tuple[str, str]:
    stamp = t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d}"
    ip = f"203.0.113.{rng.randint(1, 254)}"
    return stamp, (f'{ip} - - [{t.strftime("%d/%b/%Y:%H:%M:%S")} +0700] "{method} {path} HTTP/1.1" '
                   f'{status} {rng.randint(200, 4000)} {rng.uniform(0.01, 1.2):.3f} req={req}')


def _build_day(rng: random.Random, day: str, f: dict[str, list]) -> None:
    incident = day == INCIDENT_DAY
    inc_start = _ts(day, 19 * 3600 + 58 * 60 + 3.12)
    inc_end = _ts(day, 21 * 3600 + 4 * 60 + 40.5)

    if incident:
        f["payment-service"].append(_app(inc_start, "WARN", "payment-service",
            "config reloaded by deploy-bot: gateway.vnpay.timeout_ms 3000 -> 300 (release r2025.03.14-2)"))
        f["payment-service"].append(_app(inc_end, "INFO", "payment-service",
            "config reloaded by oncall: gateway.vnpay.timeout_ms 300 -> 3000 (rollback of r2025.03.14-2)"))

    # Orders and payments: ~650 checkouts a day, busier in the evening
    for _ in range(650):
        hour = rng.choices(range(24), weights=[1, 1, 1, 1, 1, 2, 3, 5, 6, 6, 6, 6, 7, 6, 5, 5, 6, 7, 8, 10, 12, 10, 6, 3])[0]
        t = _ts(day, hour * 3600 + rng.uniform(0, 3599))
        oid, req = rng.randint(1, 3000), f"r-{rng.getrandbits(32):08x}"
        amount = rng.randrange(50, 9000) * 1000
        gateway = rng.choice(["vnpay", "vnpay", "momo"])
        latency = rng.randint(140, 950) if gateway == "vnpay" else rng.randint(80, 600)
        f["nginx"].append(_nginx(t, rng, "POST", "/api/orders", 201, req))
        f["order-service"].append(_app(t, "INFO", "order-service", f"req={req} order_id={oid} msg=\"order created\" amount={amount}"))
        t2 = t + timedelta(milliseconds=rng.randint(30, 200))
        broken = incident and inc_start <= t2 < inc_end and gateway == "vnpay" and latency > 300
        if broken or (gateway == "vnpay" and rng.random() < 0.004):  # rare background timeouts
            for attempt in (1, 2):
                ta = t2 + timedelta(milliseconds=attempt * 320)
                limit = 300 if broken else 3000
                f["payment-service"].append(_app(ta, "ERROR", "payment-service",
                    f"req={req} order_id={oid} gateway={gateway} code=PAY_GATEWAY_TIMEOUT "
                    f"msg=\"gateway did not respond within {limit}ms (attempt {attempt}/2)\""))
            te = t2 + timedelta(milliseconds=700)
            f["nginx"].append(_nginx(te, rng, "POST", "/api/payment/charge", 504, req))
            f["order-service"].append(_app(te, "ERROR", "order-service",
                f"req={req} order_id={oid} code=ORDER_PAYMENT_FAILED msg=\"payment failed, order cancelled\""))
        elif rng.random() < 0.03:
            f["payment-service"].append(_app(t2, "WARN", "payment-service",
                f"req={req} order_id={oid} gateway={gateway} code=CARD_DECLINED msg=\"issuer declined\""))
            f["nginx"].append(_nginx(t2, rng, "POST", "/api/payment/charge", 402, req))
        else:
            f["payment-service"].append(_app(t2, "INFO", "payment-service",
                f"req={req} order_id={oid} gateway={gateway} msg=\"charge ok\" latency_ms={latency}"))
            f["nginx"].append(_nginx(t2, rng, "POST", "/api/payment/charge", 200, req))
            f["inventory-service"].append(_app(t2 + timedelta(milliseconds=50), "INFO", "inventory-service",
                f"req={req} order_id={oid} msg=\"stock reserved\" sku=SKU-{rng.randint(1, 50):03d}"))

    # Background noise: health checks, browsing, small background errors
    for service in ("order-service", "payment-service", "inventory-service"):
        for minute in range(0, 24 * 60, 1):
            t = _ts(day, minute * 60 + rng.uniform(0, 5))
            f[service].append(_app(t, "DEBUG", service, "msg=\"health check ok\" status=UP"))
    for _ in range(2200):
        t = _ts(day, rng.uniform(0, 86399))
        path = rng.choice(["/", "/products", "/products/" + str(rng.randint(1, 50)), "/cart", "/search?q=ao"])
        f["nginx"].append(_nginx(t, rng, "GET", path, rng.choice([200] * 30 + [404, 304]), f"r-{rng.getrandbits(32):08x}"))
    for _ in range(rng.randint(3, 6)):
        t = _ts(day, rng.uniform(0, 86399))
        f["payment-service"].append(_app(t, "ERROR", "payment-service",
            f"code=INVALID_SIGNATURE gateway=momo msg=\"callback signature mismatch\""))
    for _ in range(rng.randint(15, 25)):
        t = _ts(day, rng.uniform(0, 86399))
        f["inventory-service"].append(_app(t, "WARN", "inventory-service",
            f"code=LOW_STOCK sku=SKU-{rng.randint(1, 50):03d} msg=\"stock below threshold\""))
    lag_burst = 70 if incident else 0  # red herring: noisy, but unrelated to payments
    for i in range(rng.randint(8, 14) + lag_burst):
        base = 20 * 3600 + 25 * 60 if i < lag_burst else rng.uniform(0, 86399)
        t = _ts(day, base + (rng.uniform(0, 600) if i < lag_burst else 0))
        f["inventory-service"].append(_app(t, "ERROR", "inventory-service",
            f"code=STOCK_SYNC_LAG msg=\"warehouse sync behind by {rng.randint(30, 400)}s\""))


# ---------------------------------------------------------------- raw API (Code Mode SDK uses these)
def _ensure() -> None:
    if not LOG_DIR.exists() or not any(LOG_DIR.glob("*.log")):
        build()


def _path(file: str) -> Path:
    p = (LOG_DIR / file).resolve()
    if p.parent != LOG_DIR.resolve() or not p.exists():
        raise FileNotFoundError(f"log '{file}' does not exist. Use list_logs.")
    return p


def names() -> list[str]:
    _ensure()
    return sorted(p.name for p in LOG_DIR.glob("*.log"))


def lines(file: str) -> list[str]:
    _ensure()
    return _path(file).read_text(encoding="utf-8").splitlines()


def grep(pattern: str, file: str | None = None) -> list[tuple[str, int, str]]:
    rx = re.compile(pattern)
    return [(name, i, line) for name in ([file] if file else names())
            for i, line in enumerate(lines(name), 1) if rx.search(line)]


def parse(line: str) -> dict | None:
    """Split an app log line into date, time, level, service, fields (key=value) and msg."""
    m = LINE_RE.match(line)
    if not m:
        return None
    rest = m.group(5)
    fields = dict(re.findall(r'(\w+)=("[^"]*"|\S+)', rest))
    return {"date": m.group(1), "time": m.group(2), "level": m.group(3), "service": m.group(4),
            **{k: v.strip('"') for k, v in fields.items()}}


# ---------------------------------------------------------------- native tools (text into context)
def list_logs() -> str:
    out = []
    for name in names():
        p = LOG_DIR / name
        out.append(f"{name}  ({sum(1 for _ in p.open(encoding='utf-8'))} lines, {p.stat().st_size // 1024} KB)")
    return "\n".join(out)


def read_log(file: str, offset: int = 1, limit: int = MAX_READ) -> str:
    try:
        all_lines = lines(file)
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    offset, limit = max(1, int(offset)), max(1, min(int(limit), MAX_READ))
    chunk = all_lines[offset - 1: offset - 1 + limit]
    end = offset + len(chunk) - 1
    note = f"(lines {offset}-{end} of {len(all_lines)}"
    note += f"; max {MAX_READ} per call, continue with offset={end + 1})" if end < len(all_lines) else ")"
    return note + "\n" + "\n".join(chunk)


def grep_log(pattern: str, file: str = "") -> str:
    try:
        hits = grep(pattern, file or None)
    except (re.error, FileNotFoundError) as e:
        return f"ERROR: {e}"
    shown = hits[:MAX_GREP]
    head = f"{len(hits)} matching line(s)" + (f", showing first {MAX_GREP}" if len(hits) > MAX_GREP else "")
    return head + "\n" + "\n".join(f"{n}:{i}: {line}" for n, i, line in shown)


# ---------------------------------------------------------------- ground truth
def truth() -> None:
    import db
    day_lines = [(n, parse(l)) for n in names() if INCIDENT_DAY in n for l in lines(n)]
    errors = Counter(p["service"] for _, p in day_lines if p and p["level"] == "ERROR")
    print(f"ERROR lines per service on {INCIDENT_DAY}:", dict(errors.most_common()))
    top = errors.most_common(1)[0][0]
    codes = Counter(p.get("code") for _, p in day_lines if p and p["service"] == top and p["level"] == "ERROR")
    print(f"Top error codes in {top}:", dict(codes.most_common()))
    timeouts = [p for _, p in day_lines if p and p.get("code") == "PAY_GATEWAY_TIMEOUT"]
    print("PAY_GATEWAY_TIMEOUT lines per hour:", dict(sorted(Counter(p["time"][:2] for p in timeouts).items())))
    cfg = [l for n in names() if INCIDENT_DAY in n for l in lines(n) if "config reloaded" in l]
    print("Config changes:", *cfg, sep="\n  ")
    failed = sorted({int(p["order_id"]) for _, p in day_lines
                     if p and p.get("code") == "ORDER_PAYMENT_FAILED"})
    print(f"Orders failed with ORDER_PAYMENT_FAILED on {INCIDENT_DAY}: {len(failed)} distinct order_id")
    print(db.run_sql(f"SELECT COUNT(*) n_orders, SUM(total_amount) sum_total_amount FROM orders "
                     f"WHERE order_id IN ({','.join(map(str, failed))})"))


if __name__ == "__main__":
    if "--truth" in sys.argv:
        truth()
    else:
        build()
        print(f"Built {LOG_DIR}:\n{list_logs()}")
