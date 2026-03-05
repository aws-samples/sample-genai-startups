from bedrock_agentcore.runtime import BedrockAgentCoreApp
from smolagents import ToolCallingAgent, tool, AmazonBedrockModel
from bedrock_model import BedrockConverseModel
import os
import boto3

aws_region = os.getenv("AWS_REGION", "us-east-1")
model_id = "global.anthropic.claude-sonnet-4-6"
client = boto3.client('bedrock-runtime', region_name=aws_region)

app = BedrockAgentCoreApp()

model = BedrockConverseModel(
    model_id=model_id,
    region_name="us-east-1",
)

# model = AmazonBedrockModel(
#     model_id=model_id,
#     client=client
# )

@tool
def add_numbers(a: int, b: int) -> int:
    """Return the sum of two numbers.

    Args:
        a: First number.
        b: Second number.
    """
    return a + b


agent = ToolCallingAgent(
    model=model,
    tools=[add_numbers],
    # instructions="You are a helpful assistant. Use tools when appropriate.",
)


@app.entrypoint
async def invoke(payload: dict) -> dict:
    result = agent.run(payload.get("prompt", ""))
    return {"response": str(result)}


if __name__ == "__main__":
    app.run()
