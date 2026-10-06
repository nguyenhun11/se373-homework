from langchain_openai import ChatOpenAI
import os

from src.tool_registry import tools

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    raise RuntimeError("Set the OPENROUTER_API_KEY environment variable before running the app.")

llm = ChatOpenAI(
    model = "nvidia/nemotron-3-ultra-550b-a55b:free",
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1",
    temperature=0,
)

llm_with_tools = llm.bind_tools(tools)
