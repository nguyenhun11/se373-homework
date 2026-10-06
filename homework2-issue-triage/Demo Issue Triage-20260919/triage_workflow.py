"""Application-controlled Issue Triage workflow shared by CLI and Streamlit demos."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

COMPONENT_OWNERS = {
    "payment": "checkout-platform",
    "identity": "identity-platform",
    "search": "search-platform",
}
FUNCTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_component_owner",
            "description": (
                "Trả team chịu trách nhiệm cho một software component. "
                "Chỉ dùng component trong danh sách schema."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "component": {
                        "type": "string",
                        "enum": list(COMPONENT_OWNERS),
                    }
                },
                "required": ["component"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
]
SYSTEM_PROMPT = (
    "Bạn hỗ trợ triage issue phần mềm. Khi cần biết team xử lý một component, "
    "hãy gọi get_component_owner. Component hợp lệ là payment, identity hoặc "
    "search. Không tự thực thi tool."
)


@dataclass(frozen=True)
class ToolTrace:
    """One validated tool request and the application result returned to the model."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    result: dict[str, str]


@dataclass(frozen=True)
class TriageResult:
    """Consumer-facing result of a complete, single-round Issue Triage run."""

    tool_traces: tuple[ToolTrace, ...]
    final_response: str


def get_component_owner(component: str) -> str:
    """Return the owner only for application-approved components."""
    return COMPONENT_OWNERS[component]


def execute_tool_call(name: str, raw_arguments: str) -> dict[str, str]:
    """Validate a requested tool and its semantics before application execution."""
    if name != "get_component_owner":
        raise ValueError(f"Tool is not allowed: {name}")

    arguments = json.loads(raw_arguments)
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    if set(arguments) != {"component"} or not isinstance(arguments["component"], str):
        raise ValueError("Tool arguments must contain exactly one string: component.")

    component = arguments["component"]
    if component not in COMPONENT_OWNERS:
        raise ValueError(f"Unknown component: {component}")

    return {"component": component, "owner": get_component_owner(component)}


def triage_issue(client: OpenAI, model: str, issue: str) -> TriageResult:
    """Triage one issue, execute validated owner lookups, and return the final answer."""
    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": issue},
    ]
    first_response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=FUNCTION_TOOLS,
        tool_choice="required",
    )
    assistant_message = first_response.choices[0].message
    tool_calls = assistant_message.tool_calls or []
    if not tool_calls:
        raise RuntimeError("Model returned no tool call despite tool_choice='required'.")

    messages.append(assistant_message)
    traces: list[ToolTrace] = []
    for tool_call in tool_calls:
        arguments = json.loads(tool_call.function.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("Model sent tool arguments that are not a JSON object.")
        result = execute_tool_call(tool_call.function.name, tool_call.function.arguments)
        traces.append(
            ToolTrace(
                call_id=tool_call.id,
                name=tool_call.function.name,
                arguments=arguments,
                result=result,
            )
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    final_response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=FUNCTION_TOOLS,
    )
    return TriageResult(
        tool_traces=tuple(traces),
        final_response=final_response.choices[0].message.content or "(Model returned no text.)",
    )
