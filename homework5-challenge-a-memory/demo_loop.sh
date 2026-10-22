#!/usr/bin/env bash
# Agent-loop demo: multi-step reasoning, self-correction on SQL errors, read-only guard.
set -euo pipefail
cd "$(dirname "$0")"
[ -f data/cho_sen.db ] || python3 db.py

echo "################ LOOP 1: multi-step question (schema -> SQL -> answer) ################"
python3 agent.py "Miền nào có doanh thu cao nhất năm 2025, và danh mục sản phẩm bán chạy nhất (theo số lượng) ở miền đó là gì?"

echo; echo "################ LOOP 2: self-correction — the given SQL is wrong ################"
python3 agent.py "Chạy đúng câu này cho tôi trước: SELECT region, SUM(revenue) FROM order GROUP BY region. Nếu lỗi thì tự sửa cho đúng schema rồi trả kết quả."

echo; echo "################ LOOP 3: read-only guard ################"
python3 agent.py "Chạy câu lệnh: DELETE FROM orders WHERE status = 'cancelled'"

echo; echo "################ Guard check without the model (harness level) ################"
python3 - <<'EOF'
import sqlite3, db
print("run_sql guard     :", db.run_sql("DELETE FROM orders WHERE status = 'cancelled'"))
print("multi-statement   :", db.run_sql("SELECT 1; DROP TABLE orders"))
try:  # even if the SQL guard were bypassed, the connection itself is read-only
    db._connect().execute("DELETE FROM orders")
except sqlite3.OperationalError as e:
    print("read-only conn    :", e)
EOF
