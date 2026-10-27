#!/usr/bin/env bash
# Challenge B2 demo: the same log questions, answered in native tool mode and in Code Mode.
# Input tokens come from the provider's `usage` on every LLM call (summed per session).
set -euo pipefail
cd "$(dirname "$0")"
python3 logs.py > /dev/null   # (re)build the logs, deterministic

QUESTIONS=(
  "Ngày 2025-03-14, service nào có nhiều dòng ERROR nhất, và mã lỗi (code) phổ biến nhất của service đó là gì?"
  "Lỗi PAY_GATEWAY_TIMEOUT ngày 2025-03-14 tập trung vào giờ nào, và ngay trước đó payment-service có sự kiện gì bất thường?"
  "Các đơn hàng bị ORDER_PAYMENT_FAILED ngày 2025-03-14 là bao nhiêu đơn (order_id khác nhau), và tổng total_amount của chúng trong bảng orders là bao nhiêu?"
)
SUMMARY=()
for i in "${!QUESTIONS[@]}"; do
  for mode in native code; do
    echo "################ Q$((i + 1)) — mode=$mode ################"
    out=$(python3 agent.py --mode "$mode" "${QUESTIONS[$i]}" 2>&1)
    echo "$out"
    line=$(echo "$out" | grep '^=== session' | tail -1)
    SUMMARY+=("Q$((i + 1)) | $mode | $(echo "$line" | grep -oE '[0-9]+ LLM call' | grep -oE '[0-9]+') | $(echo "$line" | grep -oE '[0-9,]+ input tokens' | grep -oE '[0-9,]+') | $(echo "$line" | grep -oE 'final context [0-9,]+' | grep -oE '[0-9,]+')")
    echo
  done
done

echo "################ Token usage (from provider usage) ################"
echo "question | mode | LLM calls | input tokens (sum of all calls) | context at last call"
printf '%s\n' "${SUMMARY[@]}"

echo; echo "################ Ground truth (parsed directly from the files, not by the agent) ################"
python3 logs.py --truth
