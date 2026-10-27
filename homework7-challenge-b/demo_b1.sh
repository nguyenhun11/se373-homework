#!/usr/bin/env bash
# Challenge B1 demo: one long investigation session (native tools -> raw logs pile up in context).
# Run 1: compaction ON  (--context-budget 30000 -> compact between turns past 18,000 tokens, mid-turn past 27,000)
# Run 2: compaction OFF (same script) to compare context growth.
# What to check in run 1, after the compaction(s):
#   - turn 5: the agent still knows the goal, the 2 constraints, the 2 ruled-out hypotheses, the next step
#   - turn 6: correct root cause + numbers, no "restart" proposal, times written as HH:MM
set -euo pipefail
cd "$(dirname "$0")"
python3 logs.py > /dev/null
export AGENT_MAX_STEPS=12

script() {
cat <<'EOF'
Bối cảnh: tối 14/3/2025 khách phàn nàn thanh toán thất bại. Ràng buộc cho toàn bộ cuộc điều tra này: (a) KHÔNG được đề xuất restart service; (b) mọi mốc thời gian trong câu trả lời ghi dạng HH:MM. Bước 1: kiểm tra nginx log ngày 14/3, request thanh toán có lỗi 5xx không, vào khoảng mấy giờ?
Giả thuyết của tôi: lỗi do inventory-service đồng bộ kho chậm. Hãy kiểm tra log inventory-service ngày 14/3 quanh 20h để xác nhận hoặc loại trừ.
Thử giả thuyết khác: có phải do cổng thanh toán momo không? Kiểm tra lỗi của payment-service ngày 14/3 theo gateway.
Đọc log payment-service ngày 14/3 trong khoảng 19:50 đến 20:10 xem có sự kiện gì.
Dừng lại một chút: tóm tắt giúp tôi ta đang điều tra gì, các ràng buộc, những giả thuyết đã thử và đã loại trừ (vì sao), phát hiện chính, và bước tiếp theo là gì?
Kết luận nguyên nhân gốc, số đơn bị ảnh hưởng (order_id khác nhau có ORDER_PAYMENT_FAILED ngày 14/3) và tổng total_amount của các đơn đó, kèm đề xuất khắc phục.
EOF
}

echo "################ RUN 1: compaction ON (budget 30,000 tok: compact between turns at 60%, mid-turn only at 90%) ################"
script | python3 agent.py --mode native --context-budget 30000
echo; echo "################ RUN 2: compaction OFF (same turns) ################"
script | python3 agent.py --mode native

echo; echo "################ Ground truth ################"
python3 logs.py --truth
