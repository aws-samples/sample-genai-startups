from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.providers.bedrock import BedrockProvider

app = BedrockAgentCoreApp()

model = BedrockConverseModel(
    "global.anthropic.claude-sonnet-4-6",
    provider=BedrockProvider(
        region_name='us-east-1',
    ),
)

agent = Agent(
    model,
    instructions="You are a helpful assistant. Use tools when appropriate.",
)

@agent.tool_plain
def add_numbers(a: int, b: int) -> int:
    """Return the sum of two numbers."""
    return a + b


@app.entrypoint
async def invoke(payload: dict) -> dict:
    result = await agent.run(payload.get("prompt", ""))
    return {"response": result.output}


if __name__ == "__main__":
    app.run()
