from __future__ import annotations
import json
import argparse
from typing import Any, Literal
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, Field
from demo_common import get_model_name, create_openai_client
from persistent_memory import load_memory, update_convention, format_memory_for_prompt


# structured output schema
class IssueTriage(BaseModel):
    model_config = ConfigDict(extra="forbid") #khong cho phep field ngoai schema

    status: Literal["classified", "insufficient_data", "out_of_scope"]
    severity: Literal["P0", "P1", "P2", "P3"] | None = None
    component: Literal["payment", "identity", "search"] | None = None
    needs_urgent_response: bool = False
    reason: str = Field(description="Brief reason based on the issue data.")


#tool
COMPONENT_OWNERS = {
    "payment" : "checkout-platform",
    "identity" : "identity-platform",
    "search" : "search-platform"
}

FUNCTION_TOOLS = [
    {
        "type" : "function",
        "function" : {
            "name" : "get_component_owner",
            "description" : (
                "Return the team responsible for a software component. "
                "Only use components from the allowed list."
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

def get_component_owner(component: str) -> str:
    return COMPONENT_OWNERS[component]

def execute_tool_call(
        name: str,
        arguments: dict[str, Any],
) -> dict[str,str]:
    #model co goi dung tool khong?
    if name != "get_component_owner":
        raise ValueError(f"Tool is not allowed: {name}")

    #no co thuc su la dictionaty khong?
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    #dictionary dung format khong?
    if (set(arguments) != {"component"} or not isinstance(arguments["component"],str)):
        raise ValueError(
            "Tool arguments must contain exactly "
            "one string: component."
        )
    component = arguments["component"]
    #component co ton tai trong hthong khong?
    if component not in COMPONENT_OWNERS:
        raise ValueError(f"Unknown component: {component}")
    #goi tool
    owner = get_component_owner(component)
    return {
        "component" : component,
        "owner" : owner,
    }

#trace data
@dataclass(frozen=True)
class ToolTrace:
    """One tool call and its application result."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    result: dict[str, str]


@dataclass(frozen=True)
class TriageResult:
    """Final result of one Issue Triage run."""

    triage: IssueTriage
    tool_traces: tuple[ToolTrace, ...]

#prompt
SYSTEM_PROMPT = """
You are a software issue triage engineer.

Tasks:
- Classify the issue based on the provided information.
- Choose a severity level from P0, P1, P2, or P3 when enough information is available.
- If there is not enough information to classify the issue, use
  status=insufficient_data instead of guessing.
- If the component cannot be identified from the issue description,
  leave component as null and do not call the get_component_owner tool.
- Use status=out_of_scope only when the content is not a software issue.
- The component may be payment, identity, or search when it can be identified.
- When you need to know the team responsible for a component,
  call the get_component_owner tool.
- Do not execute the tool yourself.

After receiving the tool result, return the triage result
according to the IssueTriage schema.
"""

#main
def create_triage_issue(
        client: Any,
        model: str,
        issue: str,
        memory_context: str | None = None
) -> TriageResult:
    # Persistent memory is loaded from disk by the harness and injected into this request.
    injected_system_prompt = SYSTEM_PROMPT
    if memory_context:
        injected_system_prompt += "\n\nPERSISTENT PROJECT MEMORY\n" + memory_context
    messages: list[Any] = [
        {
            "role": "system",
            "content": injected_system_prompt,
        },
        {
            "role": "user",
            "content": issue,
        },
    ]

    # Model decides whether a tool call is needed
    first_response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=FUNCTION_TOOLS,
        tool_choice="auto",
    )

    assistant_message = first_response.choices[0].message
    tool_calls = assistant_message.tool_calls or []

    if tool_calls:
        messages.append(assistant_message)
    traces: list[ToolTrace] = []

    # Application executes the tool if the model requested one
    for tool_call in tool_calls:

        arguments = json.loads(
            tool_call.function.arguments
        )

        if not isinstance(arguments, dict):
            raise ValueError(
                "Tool arguments must be a JSON object."
            )

        result = execute_tool_call(
            tool_call.function.name,
            arguments,
        )

        trace = ToolTrace(
            call_id=tool_call.id,
            name=tool_call.function.name,
            arguments=arguments,
            result=result,
        )

        traces.append(trace)

        # Tool result goes back to model
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(
                    result,
                    ensure_ascii=False,
                ),
            }
        )

    # Model returns structured output
    final_response = client.beta.chat.completions.parse(
        model=model,
        messages=messages,
        response_format=IssueTriage,
    )

    parsed = final_response.choices[0].message.parsed

    if parsed is None:
        raise RuntimeError(
            "Model did not return a structured IssueTriage response."
        )

    # Verify that the final component is consistent with tool results.
    tool_components = {
        trace.result["component"]
        for trace in traces
    }

    if (
        parsed.component is not None
        and tool_components
        and parsed.component not in tool_components
    ):
        raise ValueError(
            "Final component does not match the component "
            f"returned by the tool: {parsed.component!r} "
            f"vs {sorted(tool_components)!r}"
        )

    return TriageResult(
        triage=parsed,
        tool_traces=tuple(traces),
    )

#CLI
DEFAULT_ISSUE = """Payment button returns HTTP 500 for all Visa cards since 14:30.
Please triage this issue and identify the responsible team."""
def main() -> None:
    parser = argparse.ArgumentParser(description="Issue Triage mini-app.")
    parser.add_argument(
        "--issue",
        default=DEFAULT_ISSUE,
        help="Issue description to triage.",
    )
    parser.add_argument(
        "--remember",
        metavar="KEY=VALUE",
        help="Create/update a persistent project convention, e.g. severity_policy='Use P1 for all payment outages'.",
    )
    parser.add_argument(
        "--show-memory",
        action="store_true",
        help="Print the currently saved project conventions and exit.",
    )
    args = parser.parse_args()
    if args.remember:
        if "=" not in args.remember:
            parser.error("--remember must use KEY=VALUE format")
        key, value = args.remember.split("=", 1)
        update_convention(key, value)
        print(f"Saved project convention: {key.strip()} = {value.strip()}")
        return

    memory = load_memory()
    if args.show_memory:
        print(format_memory_for_prompt(memory))
        if memory.get("history"):
            print("\nRecent updates:")
            for item in memory["history"][-5:]:
                print(f"- {item['key']}: {item.get('old_value')!r} -> {item['new_value']!r} ({item['updated_at']})")
        return
    
    client = create_openai_client()
    model = get_model_name()
    print("MODEL =", model)
    print("Persistent project memory loaded from:", "project_memory.json")
    print(format_memory_for_prompt(memory))

    result =  create_triage_issue(
        client,
        model,
        args.issue,
        memory_context=format_memory_for_prompt(memory),
    )

    #print required trace
    for trace in result.tool_traces:
        print("=== 1. Model suggests tool call ===")
        print(
            json.dumps(
                {
                    "id" : trace.call_id,
                    "name" : trace.name,
                    "arguments" : trace.arguments,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print("=== 2. Application executes ===")
        print(
            f"get_component_owner("
            f"{trace.result['component']!r}"
            f") -> "
            f"{trace.result['owner']!r}"
        )
        print("=== 3. Tool result goes back to model ===")
        print(
            json.dumps(
                trace.result,
                ensure_ascii=False,
                indent=2,
            )
        )

    #print final structured output
    print("\n=== 4. Final IssueTriage ===")
    print(
        result.triage.model_dump_json(
            indent=2
        )
    )

if __name__ == "__main__":
    main()