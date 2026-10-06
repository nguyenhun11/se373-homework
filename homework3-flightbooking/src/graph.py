
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from src.flight_state import FlightState
from src.llm_call import llm_call
from src.tool_registry import tools

builder = StateGraph(FlightState)

builder.add_node("llm_call", llm_call)
builder.add_node("tools", ToolNode(tools))

builder.add_edge(START, "llm_call")

builder.add_conditional_edges(
    "llm_call",
    tools_condition,
)

builder.add_edge("tools", "llm_call")

graph = builder.compile(checkpointer=InMemorySaver())