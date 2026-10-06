import argparse

from demo_common import get_client, get_model


SAMPLE_ISSUE = "Khách hàng không thanh toán được bằng thẻ Visa, hệ thống trả HTTP 500 từ 14:30."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", default=SAMPLE_ISSUE)
    args = parser.parse_args()

    answer = get_client().chat.completions.create(
        model=get_model(),
        messages=[
            {"role": "system", "content": "Bạn hỗ trợ phân loại sự cố phần mềm."},
            {"role": "user", "content": args.issue},
        ],
    )
    print(answer.choices[0].message.content)


if __name__ == "__main__":
    main()
