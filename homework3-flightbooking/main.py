from src.graph import graph
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
config: RunnableConfig = {
    "configurable": {"thread_id": "terminal-session"}
}
def main():
    print("Flight Booking Agent")
    print("Type 'exit' to quit.\n")
    while True:
        user_input = input("You: ")

        if user_input.lower() == "exit":
            break
        result = graph.invoke({
            "messages": [
                HumanMessage(content=user_input)
            ]
        } , config=config)
        response = result["messages"][-1]
        print(f"Agent: {response.content}\n")
if __name__ == "__main__":
    main()