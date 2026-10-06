from langchain.messages import SystemMessage

from src.prompt import SYSTEM_PROMPT
from src.flight_state import FlightState
from src.llm import llm_with_tools

def llm_call(state: FlightState):
    """
        Process the conversation and decide whether to respond to the user
        or call an available flight-related tool.
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *state["messages"]
    ]
    response = llm_with_tools.invoke(messages)
    return {
        "messages": [response]
    }