import argparse
import time
from typing import Literal

from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from demo_common import get_client, get_model


DEFAULT_ISSUE = "Dịch vụ thanh toán trả HTTP 500 cho toàn bộ giao dịch Visa từ 14:30."
MAX_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 10


class IssueResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["classified", "insufficient_data", "out_of_scope"]
    severity: Literal["P0", "P1", "P2", "P3"] | None = None
    component: str | None = None
    urgent: bool = False
    reason: str = Field(min_length=1)


def validation_message(error):
    messages = []
    for item in error.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "JSON root"
        message = f"field={location}; reason={item['msg']}"
        value = item.get("input")
        if isinstance(value, str):
            message += f"; response={value[:300]!r}"
        messages.append(message)
    return "\n".join(messages)


def get_prompt_only_result(client, model, issue):
    messages = [
        {
            "role": "system",
            "content": "Phân loại issue phần mềm. Chỉ trả về một JSON object, không Markdown.",
        },
        {"role": "user", "content": issue},
    ]
    try:
        response = client.chat.completions.create(model=model, messages=messages)
        return response.choices[0].message.content or ""
    except APIError as error:
        print(f"=== Prompt-only response ===\n{type(error).__name__}: {error}")
    except Exception as error:
        print(f"=== Prompt-only response ===\n{type(error).__name__}: {error}")
    return None


def get_structured_result(client, model, issue):
    messages = [
        {
            "role": "system",
            "content": "Bạn là kỹ sư phụ trách phân loại sự cố phần mềm. Phân loại severity theo P0/P1/P2/P3 dựa trên dữ liệu issue. Nếu dữ liệu không đủ để phân loại, dùng status=insufficient_data thay vì đoán. Chỉ dùng status=out_of_scope khi nội dung không phải issue phần mềm. Chỉ trả về một JSON object đúng schema. Không Markdown, không giải thích, không có text ngoài JSON.",
        },
        {"role": "user", "content": issue},
    ]

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=IssueResult,
            )
            result = response.choices[0].message.parsed
            if result is not None:
                return result
            print(f"\nAttempt {attempt + 1}/{MAX_ATTEMPTS}: parsed result is empty.")
        except ValidationError as error:
            print(
                f"\nAttempt {attempt + 1}/{MAX_ATTEMPTS}: ValidationError\n"
                f"{validation_message(error)}"
            )
        except APIError as error:
            print(f"\nAttempt {attempt + 1}/{MAX_ATTEMPTS}: {type(error).__name__}: {error}")
        except Exception as error:
            print(f"\nAttempt {attempt + 1}/{MAX_ATTEMPTS}: {type(error).__name__}: {error}")
            return None

        if attempt == MAX_ATTEMPTS - 1:
            break

        for seconds_left in range(RETRY_DELAY_SECONDS, 0, -1):
            print(
                f"\rAttempt {attempt + 1}/{MAX_ATTEMPTS} was unsuccessful. "
                f"Retrying in {seconds_left:02d} seconds...",
                end="",
                flush=True,
            )
            time.sleep(1)
        print()

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", default=DEFAULT_ISSUE)
    issue = parser.parse_args().issue

    try:
        client = get_client()
        model = get_model()
    except Exception as error:
        print(f"Lỗi khởi tạo: {type(error).__name__}: {error}")
        return

    prompt_only = get_prompt_only_result(client, model, issue)
    if prompt_only is not None:
        print("=== Prompt-only response ===")
        print(prompt_only)

    result = get_structured_result(client, model, issue)
    if result is None:
        print("Không nhận được structured output hợp lệ.")
        return

    print("=== Structured output ===")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
