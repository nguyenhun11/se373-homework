import argparse
import json

from demo_common import get_client, get_model
from triage_workflow import triage


DEFAULT_ISSUE = "Tất cả giao dịch Visa bị HTTP 500 từ 14:30. Hãy phân loại lỗi và tìm team xử lý."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", default=DEFAULT_ISSUE)
    issue = parser.parse_args().issue
    result = triage(get_client(), get_model(), issue)

    for item in result.logs:
        print("=== Tool call từ model ===")
        print(json.dumps({"id": item.call_id, "name": item.tool_name, "arguments": item.arguments}, ensure_ascii=False, indent=2))
        print("=== Kết quả tool trong application ===")
        print(f"get_component_owner({item.arguments['component']!r})")
        print("=== Tool result quay lại model ===")
        print(json.dumps(item.output, ensure_ascii=False, indent=2))

    print("=== Phản hồi cuối cùng ===")
    print(result.answer)


if __name__ == "__main__":
    main()
