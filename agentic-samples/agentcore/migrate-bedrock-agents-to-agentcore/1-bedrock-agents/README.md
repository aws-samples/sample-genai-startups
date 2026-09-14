# Phase 1 — Amazon Bedrock Agents

This directory contains a Bedrock Agent deployed with AWS CDK that handles private jet reservation requests.

## Architecture

![Phase 1 architecture: caller invokes Bedrock Agents with an input prompt; the managed orchestration loop routes to three action groups, each backed by a dedicated Lambda function (GetOwnerInfo, GetPassengers, BookReservation); CloudWatch Logs captures agent-level traces](docs/architecture.png)

The managed orchestration loop inside [Amazon Bedrock Agents](https://aws.amazon.com/bedrock/agents/) takes the user prompt, the system instructions, and the action-group schemas, and decides which Lambda function to invoke at each step. Each of the three tools is implemented as a dedicated [AWS Lambda](https://aws.amazon.com/lambda/) function, packaged by CDK. Agent-level traces stream to [Amazon CloudWatch](https://aws.amazon.com/cloudwatch/) Logs.

Components:

- **3 Lambda functions**: `GetOwnerInfo`, `GetPassengers`, `BookReservation`
- **3 action groups**, one per Lambda. Each action group uses a `functionSchema` (not `apiSchema`). `functionSchema` is the format the AgentCore CLI import path translates into `@tool` scaffolding in Phase 2.
- **1 CDK stack**: IAM roles, Lambda functions, Bedrock Agent, Agent Alias
- **Model**: `us.anthropic.claude-sonnet-4-6` (cross-region inference profile) on Amazon Bedrock

The Lambda functions use the `functionSchema` event shape. Parameters arrive as `event["parameters"]` (a list of `{name, type, value}` entries). Responses return `{"messageVersion": "1.0", "response": {"actionGroup", "function", "functionResponse": {"responseBody": {"TEXT": {"body": "<result>"}}}}}`.

The `api_schemas/` directory contains per-operation OpenAPI 3.0 schemas for reference. Bedrock Agents supports both `apiSchema` and `functionSchema`, but the AgentCore CLI import only translates `functionSchema`-based action groups into generated `@tool` stubs.

## Deploy

```bash
cd cdk
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PATH=".venv/bin:$PATH" cdk bootstrap   # if first time in this account/region
PATH=".venv/bin:$PATH" cdk deploy
```

## Test

```bash
python3 invoke_agent.py
```

Reads the Agent ID and Alias ID from CloudFormation outputs and sends the booking prompt.

## Sample Prompt

> Mr. John Doe (OwnerId: 9612f6c4-b7ff-4d82-b113-7b605e188ed9) is planning for a surprise trip to Disney World in 5 hours with his family. Please book a reservation for them.

The agent should:
1. Look up John Doe's profile (home airport: KJFK)
2. Retrieve his family members (Jill, Jane, Jenny)
3. Reason that Disney World → KMCO, compute departure time
4. Book the reservation with all passengers

## Clean up

```bash
cd cdk
PATH=".venv/bin:$PATH" cdk destroy

# The CloudWatch log group survives cdk destroy — remove it to stop
# charges and to allow a clean redeploy.
aws logs delete-log-group \
  --log-group-name /aws/bedrock/agents/PrivateAviationAgent \
  --region us-east-1
```

`cdk destroy` removes the agent, alias, three Lambdas, and IAM roles. The log group under `/aws/bedrock/agents/PrivateAviationAgent` is retained by CloudFormation to preserve execution history — delete it separately.
