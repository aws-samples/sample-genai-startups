"""Test script for the Private Aviation Bedrock Agent.

Reads AgentId and AgentAliasId from CloudFormation stack outputs
and sends the aviation booking prompt.

The current UTC time is injected into the prompt so the agent can compute
concrete departure times from relative phrases like "in 5 hours". Bedrock
Agents does not expose a built-in clock tool, and the agent's foundation
model only knows its training-data cutoff — without this, the booking
date hallucinates to whatever the model was trained on.
"""

import boto3
import uuid
from datetime import datetime, timezone

STACK_NAME = "PrivateAviationAgentStack"
REGION = "us-east-1"

USER_REQUEST = (
    "Mr. John Doe (OwnerId: 9612f6c4-b7ff-4d82-b113-7b605e188ed9) is planning "
    "for a surprise trip to Disney World in 5 hours with his family. "
    "Please book a reservation for them."
)


def build_prompt() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return (
        f"Current time: {now.isoformat()} (UTC). "
        f"Use this as the reference for any relative time expressions.\n\n"
        f"{USER_REQUEST}"
    )


def get_stack_outputs():
    cfn = boto3.client("cloudformation", region_name=REGION)
    resp = cfn.describe_stacks(StackName=STACK_NAME)
    outputs = resp["Stacks"][0]["Outputs"]
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def invoke_agent(agent_id, alias_id, prompt):
    client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    session_id = str(uuid.uuid4())

    response = client.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=session_id,
        inputText=prompt,
    )

    result = ""
    for event in response["completion"]:
        if "chunk" in event:
            result += event["chunk"]["bytes"].decode("utf-8")
    return result


def main():
    print("Reading stack outputs...")
    outputs = get_stack_outputs()
    agent_id = outputs["AgentId"]
    alias_id = outputs["AgentAliasId"]
    print(f"Agent ID: {agent_id}")
    print(f"Alias ID: {alias_id}")

    prompt = build_prompt()
    print(f"\nPrompt:\n{prompt}\n")
    print("Invoking agent...\n")

    response = invoke_agent(agent_id, alias_id, prompt)
    print("Response:")
    print(response)


if __name__ == "__main__":
    main()
