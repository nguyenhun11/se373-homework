"""Sample "Chợ Sen" database (fake data) and a read-only query helper.

Read-only is enforced at the connection level (SQLite `mode=ro`), not only
in the prompt — writes fail even if the SQL guard below is bypassed.
"""

from __future__ import annotations

import random
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "cho_sen.db"
MAX_ROWS = 20  # rows returned to the LLM; the rest is summarised, not dumped into context

REGIONS = {"Bắc": ["Hà Nội", "Hải Phòng"], "Trung": ["Đà Nẵng", "Huế"], "Nam": ["TP.HCM", "Cần Thơ"]}
CATEGORIES = ["Điện thoại", "Thời trang", "Gia dụng", "Sách", "Mỹ phẩm"]
STATUSES = ["delivered"] * 7 + ["cancelled", "returned", "shipping"]


def build(seed: int = 373) -> None:
    """Create a small deterministic database (same seed -> same numbers)."""
    rng = random.Random(seed)
    DB_PATH.parent.mkdir(exist_ok=True)
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, full_name TEXT, province TEXT, region TEXT);
        CREATE TABLE products  (product_id INTEGER PRIMARY KEY, product_name TEXT, category TEXT, unit_price INTEGER);
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers,
            order_date TEXT,            -- ISO 'YYYY-MM-DD'
            status TEXT,                -- delivered | cancelled | returned | shipping
            total_amount INTEGER,       -- VND, before discount
            discount_amount INTEGER     -- VND
        );
        CREATE TABLE order_items (
            order_id INTEGER REFERENCES orders, product_id INTEGER REFERENCES products,
            quantity INTEGER, unit_price INTEGER
        );
        """
    )
    names = ["Nguyễn An", "Trần Bình", "Lê Chi", "Phạm Dũng", "Hoàng Giang", "Vũ Hà", "Đặng Khoa", "Bùi Lan"]
    customers = []
    for cid in range(1, 201):
        region = rng.choice(list(REGIONS))
        customers.append((cid, f"{rng.choice(names)} {cid}", rng.choice(REGIONS[region]), region))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?)", customers)

    products = [(pid, f"Sản phẩm {pid}", rng.choice(CATEGORIES), rng.randrange(50, 5000) * 1000) for pid in range(1, 51)]
    con.executemany("INSERT INTO products VALUES (?,?,?,?)", products)

    start = date(2025, 1, 1)
    for oid in range(1, 3001):
        items = [(oid, p[0], rng.randint(1, 3), p[3]) for p in rng.sample(products, rng.randint(1, 3))]
        total = sum(q * price for _, _, q, price in items)
        discount = rng.choice([0, 0, 0.05, 0.1, 0.2]) * total
        con.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?,?)",
            (oid, rng.randint(1, 200), (start + timedelta(days=rng.randrange(0, 365))).isoformat(),
             rng.choice(STATUSES), total, int(discount)),
        )
        con.executemany("INSERT INTO order_items VALUES (?,?,?,?)", items)
    con.commit()
    con.close()


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        build()
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


_ALLOWED = re.compile(r"^\s*(select|with)\b", re.I)


def run_sql(sql: str) -> str:
    sql = sql.strip().rstrip(";")
    if ";" in sql:
        return "ERROR: only one statement is allowed."
    if not _ALLOWED.match(sql):
        return "ERROR: read-only agent — only SELECT / WITH queries are allowed."
    try:
        with _connect() as con:
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(MAX_ROWS + 1)
    except sqlite3.Error as e:
        return f"SQL ERROR: {e}"
    shown = rows[:MAX_ROWS]
    lines = [" | ".join(cols)] + [" | ".join(str(v) for v in r) for r in shown]
    if len(rows) > MAX_ROWS:
        lines.append(f"... (truncated, more than {MAX_ROWS} rows — add GROUP BY / LIMIT)")
    return f"{len(shown)} row(s):\n" + "\n".join(lines)


def query(sql: str, max_rows: int = 10_000) -> list[dict]:
    """Structured variant for Code Mode programs: rows stay in the runtime, not in the context."""
    sql = sql.strip().rstrip(";")
    if ";" in sql or not _ALLOWED.match(sql):
        raise ValueError("read-only: only one SELECT / WITH query is allowed")
    with _connect() as con:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchmany(max_rows)]


def list_tables() -> str:
    with _connect() as con:
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return ", ".join(r[0] for r in rows)


def describe_table(table: str) -> str:
    with _connect() as con:
        row = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not row:
            return f"ERROR: table '{table}' does not exist. Tables: {list_tables()}"
        sample = con.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall()
    return f"{row[0]}\nSample rows: {sample}"


if __name__ == "__main__":
    build()
    print(f"Built {DB_PATH}: {list_tables()}")
