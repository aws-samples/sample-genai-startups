from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_aws import ChatBedrockConverse
from langchain.agents import create_agent
from langchain.tools import tool

app = BedrockAgentCoreApp()

model = ChatBedrockConverse(
    model="global.anthropic.claude-sonnet-4-6",
    region_name="us-east-1",
)


@tool
def add_numbers(a: int, b: int) -> int:
    """Return the sum of two numbers."""
    return a + b


# create_agent builds a graph-based agent using LangGraph under the hood:
#   START → model node → (tool calls?) → tools node → model node → ... → END
agent = create_agent(
    model,
    tools=[add_numbers],
    system_prompt="You are a helpful assistant. Use tools when appropriate.",
)


@app.entrypoint
async def invoke(payload: dict) -> dict:
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": payload.get("prompt", "")}]}
    )
    return {"response": result["messages"][-1].content}


if __name__ == "__main__":
    app.run()
