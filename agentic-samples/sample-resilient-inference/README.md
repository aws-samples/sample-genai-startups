# Resilient Inference with Bedrock, Strands, LiteLLM, and AgentCore

This sample is the runnable companion to
[Building inference reliability controls with Amazon Bedrock and AgentCore](../02-implementation.md).
It uses one small customer-support agent throughout: given a ticket and trusted
order context, the agent drafts a reply for human review.

The business task stays the same while the inference controls grow around it.
This makes it possible to see which reliability problem each control solves,
what evidence is needed before adding the next layer, and which responsibilities
belong to the model route, the gateway, and the agent host.

The examples make real Amazon Bedrock inference calls unless stated otherwise.
They are a reference implementation, not a benchmark or a complete production
platform.

## What the Sample Shows

| Stage | Reliability control | What the example proves |
|---|---|---|
| 1. Prototype | One Bedrock route with timeouts, bounded retries, and an output cap | The task works at an acceptable latency and token usage |
| 2. MVP | The same ticket evaluations run against a primary and fallback candidate | A fallback model preserves the behavior your users depend on |
| 3. Production routing | One LiteLLM alias owns retry and fallback policy | A forced primary failure reaches the evaluated fallback and exposes the served deployment |
| 3. Production hosting | The Strands agent runs behind an AgentCore Runtime-compatible HTTP entrypoint | Runtime hosts the agent process; it does not choose or evaluate the fallback |

The architecture changes at Stage 3:

```text
Stages 1-2
ticket -> Strands agent -> Bedrock model or inference profile

Stage 3
ticket -> AgentCore-hosted Strands agent -> LiteLLM ticket-drafter alias
                                           |-> primary Bedrock route
                                           `-> evaluated fallback route
```

LiteLLM is the inference-routing control plane. AgentCore Runtime is the managed
execution boundary for the application that calls it. The distinction matters:
a healthy Runtime does not prove that model failover works, and a successful
failover does not prove that the fallback answer is acceptable.

## Repository Map

| Path | Purpose |
|---|---|
| `src/reliable_inference/core.py` | Direct Bedrock agent, request bounds, result metadata, and evaluation rules |
| `src/reliable_inference/gateway.py` | Gateway-backed Strands agent and LiteLLM connection settings |
| `examples/stage1_prototype.py` | One bounded Bedrock route |
| `examples/stage2_mvp.py` | Primary and fallback behavioral release gate |
| `litellm-config.yaml` | Stable alias, retry budget, primary route, and fallback order |
| `examples/stage3_gateway_probe.py` | Direct gateway call that reports the served LiteLLM deployment |
| `examples/stage3_production.py` | AgentCore Runtime-compatible HTTP application |
| `tests/test_patterns.py` | Offline unit tests for the controls and contracts |

## Quick Start

Start with Stages 1 and 2. They require only one shell and demonstrate the core
idea before introducing a gateway or managed hosting.

### Requirements

- Python 3.10-3.13
- [`uv`](https://docs.astral.sh/uv/)
- AWS credentials that can invoke the selected Bedrock models
- AWS CLI for checking identity and available inference profiles
- Access to the selected profiles from your AWS Region

The defaults use `us-east-1`, a global Nova 2 Lite primary profile, and a
US-scoped Nova Micro fallback. If those profiles are not available from your
Region, replace them with profiles you can invoke.

### Install and Configure

From the repository root:

```bash
cd sample-resilient-inference
uv sync

export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=global.amazon.nova-2-lite-v1:0
export BEDROCK_CANDIDATE_MODEL_ID=us.amazon.nova-micro-v1:0
```

Confirm which AWS identity the examples will use and list the profiles available
from the configured Region:

```bash
aws sts get-caller-identity
aws bedrock list-inference-profiles \
  --region "$AWS_REGION" \
  --type-equals SYSTEM_DEFINED
```

Use `us.amazon.nova-2-lite-v1:0` for `BEDROCK_MODEL_ID` when global routing is
unavailable or the workload must remain within the profile's supported US
geography.

### Stage 1: Prove One Bounded Route

```bash
uv run python examples/stage1_prototype.py
```

The script sends one real ticket through the Strands agent and reports the draft,
model ID, latency, input and output tokens, and stop reason. The important
control is in `core.py`: the model call has finite connection and read timeouts,
a bounded adaptive retry policy, and `max_tokens=300`.

### Stage 2: Admit a Fallback

```bash
uv run python examples/stage2_mvp.py
```

The script runs the same ticket cases against `BEDROCK_MODEL_ID` and
`BEDROCK_CANDIDATE_MODEL_ID`. It blocks the release if the candidate has a lower
pass rate or violates a hard invariant, such as inventing an order ID, omitting
a required action, or claiming that a refund was processed.

Passing this gate means the candidate is safe enough for these test cases. It
does not mean the two models are behaviorally identical.

## Stage 3: Route Through LiteLLM

Stage 3 moves the evaluated routes behind the stable `ticket-drafter` alias in
`litellm-config.yaml`. LiteLLM owns the retry and fallback decision, so the
application no longer loops over model IDs.

This local flow uses three terminals:

1. Terminal 1 runs LiteLLM.
2. Terminal 2 probes the gateway and reports the deployment that served it.
3. Terminal 3 runs the AgentCore-compatible application.

> **Local sample only:** This sample runs LiteLLM on `localhost` to make the
> routing behavior easy to try. In production, host LiteLLM as a separate
> service on infrastructure such as Amazon EC2, Amazon ECS, or Amazon EKS, then
> give the AgentCore Runtime a network-reachable gateway endpoint. See the AWS
> [Multi-Provider Generative AI Gateway reference architecture](https://aws.amazon.com/blogs/machine-learning/streamline-ai-operations-with-the-multi-provider-generative-ai-gateway-reference-architecture/)
> for production deployment patterns using ECS or EKS.

### Terminal 1: Start the Gateway

```bash
export AWS_REGION=us-east-1
export LITELLM_PRIMARY_MODEL=bedrock/global.amazon.nova-2-lite-v1:0
export LITELLM_FALLBACK_MODEL=bedrock/us.amazon.nova-micro-v1:0
export LITELLM_MASTER_KEY=sk-local-development-key-change-this

uv run litellm --config litellm-config.yaml --port 4000
```

The LiteLLM process uses your AWS credentials to invoke Bedrock. The master key
shown here is only for local development.

### Terminal 2: Verify the Primary Route

```bash
export LITELLM_BASE_URL=http://localhost:4000
export LITELLM_API_KEY=sk-local-development-key-change-this

uv run python examples/stage3_gateway_probe.py
```

The probe calls the `ticket-drafter` alias and reads LiteLLM's
`x-litellm-model-id` response header. With the normal configuration,
`deployment_id` is `ticket-drafter-primary` and `fallback_used` is `False`.

### Terminal 3: Run the Agent Application

```bash
export LITELLM_BASE_URL=http://localhost:4000
export LITELLM_API_KEY=sk-local-development-key-change-this

uv run python examples/stage3_production.py
```

After the probe exits, use Terminal 2 to invoke the application:

```bash
curl -s http://localhost:8080/invocations \
  -H 'content-type: application/json' \
  -d '{"ticket":"Where is order #10042?","order_context":"Order #10042 shipped on 4 August. Tracking ID ZX-1942."}'
```

The application response reports the stable alias, latency, token usage, and
stop reason. It does not claim to know which backend served the request; use
LiteLLM's headers and telemetry for that evidence.

### Drill a Primary Failure

Stop LiteLLM in Terminal 1, replace the primary with an invalid model, and
restart it:

```bash
export LITELLM_PRIMARY_MODEL=bedrock/not-a-real-model
uv run litellm --config litellm-config.yaml --port 4000
```

Run the gateway probe again in Terminal 2. A successful drill reports:

```text
deployment_id=ticket-drafter-fallback
fallback_used=True
```

Stop LiteLLM again, restore the primary, and restart the gateway before
continuing:

```bash
export LITELLM_PRIMARY_MODEL=bedrock/global.amazon.nova-2-lite-v1:0
uv run litellm --config litellm-config.yaml --port 4000
```

The drill proves routing availability. Run the Stage 2 evaluations against the
fallback separately to prove answer quality.

## Optional: Deploy the Agent to AgentCore Runtime

Complete the local Stage 3 flow first. A deployed Runtime cannot call the
LiteLLM process on your laptop; it needs a deployed LiteLLM endpoint that is
reachable from the Runtime network.

Deployment additionally requires:

- AWS CLI v2
- Node.js 20 or later
- The AgentCore CLI
- A deployed LiteLLM endpoint
- A Secrets Manager secret containing the LiteLLM API key as its `SecretString`

Scaffold the Runtime project and copy the sample entrypoint and package into it:

```bash
npm install -g @aws/agentcore
mkdir -p agentcore-deploy
npm_config_legacy_peer_deps=true agentcore create \
  --name TicketReliability \
  --framework Strands \
  --model-provider Bedrock \
  --memory none \
  --build CodeZip \
  --protocol HTTP \
  --output-dir agentcore-deploy \
  --skip-git \
  --skip-python-setup

cp examples/stage3_production.py \
  agentcore-deploy/TicketReliability/app/TicketReliability/main.py
cp -R src/reliable_inference \
  agentcore-deploy/TicketReliability/app/TicketReliability/reliable_inference

cd agentcore-deploy/TicketReliability
uv add "strands-agents[litellm]>=1.50.0" "litellm>=1.75.9,<=1.91.1"
```

Configure the generated Runtime with:

```text
LITELLM_BASE_URL=<deployed LiteLLM endpoint>
LITELLM_API_KEY_SECRET_ID=<Secrets Manager secret name or ARN>
```

Grant the Runtime execution role `secretsmanager:GetSecretValue` only for that
secret. Do not place the LiteLLM key itself in Runtime environment variables.
The LiteLLM service role, not the Runtime role, needs permission to invoke the
selected Bedrock profiles.

Review the generated infrastructure, keep Runtime IAM authorization enabled,
and deploy:

```bash
agentcore deploy --dry-run
agentcore deploy
```

The deployment should also configure CloudWatch Logs encryption and retention.

Remove the generated resources when finished:

```bash
agentcore remove all
agentcore deploy
```

## Run the Offline Tests

The unit suite mocks model and gateway responses, so it does not call Bedrock or
create AWS resources:

```bash
uv run python -m unittest discover -s tests
```

The tests cover result metadata, deterministic evaluation rules, payload
validation, the stable gateway alias, LiteLLM deployment metadata, and the
Secrets Manager configuration path.

## Common Problems

| Symptom | Check |
|---|---|
| `AccessDeniedException` | Confirm the active AWS identity can invoke both configured Bedrock profiles |
| Model or inference profile not found | List profiles in the source Region and replace the defaults with supported IDs |
| Gateway probe cannot connect | Confirm LiteLLM is running on port 4000 and `LITELLM_BASE_URL` does not include `/v1` |
| Gateway returns 401 | `LITELLM_API_KEY` must match the gateway's `LITELLM_MASTER_KEY` |
| Runtime works but does not report the served model | This is expected; inspect LiteLLM response headers or telemetry |
