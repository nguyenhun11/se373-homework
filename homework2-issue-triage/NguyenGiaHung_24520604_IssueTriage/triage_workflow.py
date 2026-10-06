import json
from dataclasses import dataclass


OWNERS = {
    "payment": "checkout-platform",
    "identity": "identity-platform",
    "search": "search-platform",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_component_owner",
            "description": "Tìm team phụ trách một component.",
            "parameters": {
                "type": "object",
                "properties": {"component": {"type": "string", "enum": list(OWNERS)}},
                "required": ["component"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
]


@dataclass
class ToolLog:
    call_id: str
    tool_name: str
    arguments: dict
    output: dict


@dataclass
class TriageOutput:
    logs: list[ToolLog]
    answer: str


def get_component_owner(component):
    return OWNERS[component]


def call_local_tool(name, raw_arguments):
    if name != "get_component_owner":
        raise ValueError("Tool không được cho phép")
    arguments = json.loads(raw_arguments)
    if not isinstance(arguments, dict) or set(arguments.keys()) != {"component"}:
        raise ValueError("Tool phải có đúng trường component")
    component = arguments["component"]
    if not isinstance(component, str) or component not in OWNERS:
        raise ValueError("Component không hợp lệ")
    return arguments, {"component": component, "owner": get_component_owner(component)}


def triage(client, model, issue):
    messages = [
        {
            "role": "system",
            "content": "Bạn phân loại issue phần mềm. Khi cần team phụ trách, hãy dùng get_component_owner. Chỉ có payment, identity và search.",
        },
        {"role": "user", "content": issue},
    ]
    first = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOLS,
        tool_choice="required",
    )
    assistant_message = first.choices[0].message
    tool_calls = assistant_message.tool_calls or []
    if not tool_calls:
        raise RuntimeError("Model chưa gửi tool call")

    messages.append(assistant_message)
    logs = []
    for tool_call in tool_calls:
        arguments, output = call_local_tool(tool_call.function.name, tool_call.function.arguments)
        logs.append(ToolLog(tool_call.id, tool_call.function.name, arguments, output))
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(output, ensure_ascii=False),
            }
        )

    final = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
    answer = final.choices[0].message.content or "Model không có câu trả lời"
    return TriageOutput(logs, answer)
