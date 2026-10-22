#!/usr/bin/env bash
# Challenge A demo: every `python agent.py` call below is a separate process = a new session.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf memory sessions   # start from a clean slate
python3 db.py            # (re)build the sample database, deterministic data

Q="Doanh thu từng tháng của quý 1 năm 2025 là bao nhiêu?"

echo "################ SESSION 1: agree on conventions ################"
python3 agent.py --show-context "Chốt quy ước dự án: (1) doanh thu = SUM(orders.total_amount) \
của đơn có status = 'delivered'; (2) cột doanh thu đặt alias là revenue_vnd; \
(3) tháng hiển thị dạng YYYY-MM."

echo; echo "################ SESSION 2 — Proof 1: new session reuses conventions ################"
python3 agent.py --show-context "$Q"

echo; echo "################ SESSION 3: conventions change ################"
python3 agent.py --show-context "Đổi quy ước: từ nay doanh thu là doanh thu thuần \
= SUM(total_amount - discount_amount) của đơn delivered."

echo; echo "################ SESSION 4 — Proof 2: later sessions use the NEW conventions ################"
python3 agent.py --show-context "$Q"

echo; echo "################ Memory file after the change (history kept) ################"
cat memory/MEMORY.md

echo; echo "################ Ground truth (computed directly, not by the agent) ################"
python3 - <<'EOF'
import db
print("Gross (convention v1):")
print(db.run_sql("SELECT substr(order_date,1,7) m, SUM(total_amount) FROM orders WHERE status='delivered' AND order_date < '2025-04-01' GROUP BY m"))
print("Net (convention v2):")
print(db.run_sql("SELECT substr(order_date,1,7) m, SUM(total_amount-discount_amount) FROM orders WHERE status='delivered' AND order_date < '2025-04-01' GROUP BY m"))
EOF
