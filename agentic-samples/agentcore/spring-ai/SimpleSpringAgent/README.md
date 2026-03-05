# SimpleSpringAgent

This sample shows how to bring your own [Spring AI](https://spring.io/projects/spring-ai) agent to
[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) using the
[spring-ai-agentcore](https://github.com/spring-ai-community/spring-ai-agentcore) community starter.

The agent (`AgentService`) uses Spring AI's `ChatClient` with Bedrock Converse and a `@Tool`-annotated
`MathTools` class. The `spring-ai-agentcore-runtime-starter` auto-wires the AgentCore service contract
(`POST /invocations` + `GET /ping` on port 8080) via the `@AgentCoreInvocation` annotation —
the Java equivalent of Python's `BedrockAgentCoreApp`.

> **Why CDK is used directly**
>
> Java requires a custom container image (no managed `JAVA_21` CodeZip runtime exists in AgentCore CLI).
> We therefore use AWS CDK L1 constructs (`CfnRuntime` from `aws-cdk-lib/aws-bedrockagentcore`) to
> deploy directly.

## Quick Start

```bash
make test         # build Docker image and run tests against the local container
make stop         # stop and remove the local test container
make deploy       # install CDK deps and deploy to AWS
make deploy-test  # deploy to AWS and run integration tests against the live runtime
make destroy      # tear down the deployed AWS stack
```

## Project Structure

```
SimpleSpringAgent/
├── README.md
├── agentcore/
│   ├── agentcore.json      # Agent resource specification (source of truth for deployment)
│   ├── aws-targets.json    # Deployment targets (account, region)
│   └── cdk/                # CDK infrastructure — deploy directly with cdk deploy
├── app/
│   └── SpringAgent/        # Your agent code — iterate here
│       ├── pom.xml         # Spring Boot 3.4.5, Java 21, Spring AI + spring-ai-agentcore
│       ├── Dockerfile      # Multi-stage: maven builder → corretto-21-alpine runtime
│       └── src/main/
│           ├── java/com/amazon/agentcore/springagent/
│           │   ├── SpringAgentApplication.java  # Spring Boot entry point
│           │   ├── AgentService.java            # @AgentCoreInvocation handler + ChatClient
│           │   ├── PromptRequest.java           # record { String prompt }
│           │   └── MathTools.java               # @Tool addNumbers
│           └── resources/
│               └── application.properties
└── scripts/
    ├── run-local.sh        # Docker build + curl tests against port 8080
    └── test-ephemeral.sh   # CDK deploy → tests → cleanup temp files
```

## How It Works

`AgentService` is the single agent handler. `@AgentCoreInvocation` maps the method to
`POST /invocations`; the starter handles JSON deserialization of the request body into
`PromptRequest` and serializes the `String` return value as the response.

```java
@Service
public class AgentService {
    private final ChatClient chatClient;

    public AgentService(ChatClient.Builder builder) {
        this.chatClient = builder.defaultTools(new MathTools()).build();
    }

    @AgentCoreInvocation
    public String handlePrompt(PromptRequest request, AgentCoreContext context) {
        log.info("Session: {}", context.getHeader(AgentCoreHeaders.SESSION_ID));
        return chatClient.prompt().user(request.prompt()).call().content();
    }
}
```

`MathTools` demonstrates Spring AI's `@Tool` annotation, keeping parity with the other samples:

```java
public class MathTools {
    @Tool(description = "Return the sum of two numbers")
    public int addNumbers(int a, int b) { return a + b; }
}
```

**Why a custom container?**

The AgentCore CLI only supports Python CodeZip runtimes. A custom Docker image is required for Java,
so we use the L1 CDK construct `CfnRuntime` directly.

**Authentication**

The container runs with an IAM execution role provisioned by CDK. The AWS SDK default credential chain
picks up credentials automatically via the container metadata endpoint — no `AWS_ACCESS_KEY_ID` or
explicit credential provider is needed in production.

## Prerequisites

- **Docker Desktop** or a compatible runtime such as [Finch](https://runfinch.com/) — required for container builds and local testing. Finch (v1.4+) is a confirmed working alternative — use `make test DOCKER=finch`.
- **AWS CDK CLI** — install with `npm install -g aws-cdk`
- **AWS credentials** with permissions for Bedrock, ECR, IAM, and CloudFormation

## Local Testing

The `scripts/run-local.sh` script builds the Docker image and runs both test cases against the
local container using your current AWS profile credentials:

```bash
chmod +x scripts/run-local.sh
./scripts/run-local.sh
```

To use a specific AWS profile:

```bash
AWS_PROFILE=my-profile ./scripts/run-local.sh
```

The script runs two tests automatically:
1. Math tool call — `"What is 42 plus 58?"` (exercises `MathTools.addNumbers` via tool call)
2. General knowledge — `"What is the capital of France?"` (pure LLM answer, no tool needed)

To manually build and run the container:

```bash
cd app/SpringAgent
docker build --platform linux/arm64 -t spring-agent .
docker run -p 8080:8080 \
  -e AWS_REGION=us-east-1 \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  spring-agent
```

Invoke the local agent:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 42 plus 58?"}'
```

Health check:

```bash
curl http://localhost:8080/ping
```

## Deployment

### 1. Configure your AWS account

Edit `agentcore/aws-targets.json` and replace the account ID with your 12-digit AWS account ID.

### 2. Bootstrap CDK (first time only)

```bash
cd agentcore/cdk
npm install
npm run build
npx cdk bootstrap
```

### 3. Deploy the stack

```bash
npx cdk deploy
```

This builds the Docker image (multi-stage Maven build inside Docker), pushes it to ECR, creates
the IAM execution role with the required Bedrock + ECR + CloudWatch permissions, and provisions
the AgentCore Runtime. Note the `AgentRuntimeId` and `AgentRuntimeArn` output values.

### 4. Test the deployed agent

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "What is 42 plus 58?"}' \
  --content-type "application/json" \
  --cli-binary-format raw-in-base64-out \
  --endpoint-url https://bedrock-agentcore.us-east-1.amazonaws.com \
  --region us-east-1 \
  response.txt && cat response.txt
```

Run both test cases:

```bash
# Math tool call
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "What is 42 plus 58?"}' \
  --content-type "application/json" \
  --cli-binary-format raw-in-base64-out \
  --endpoint-url https://bedrock-agentcore.us-east-1.amazonaws.com \
  --region us-east-1 response.txt && cat response.txt

# General knowledge
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "What is the capital of France?"}' \
  --content-type "application/json" \
  --cli-binary-format raw-in-base64-out \
  --endpoint-url https://bedrock-agentcore.us-east-1.amazonaws.com \
  --region us-east-1 response.txt && cat response.txt
```

> **AWS CLI notes:**
> - `--endpoint-url` is required because the AWS CLI resolves `bedrock-agentcore invoke-agent-runtime`
>   to a different internal endpoint by default. Specifying the data-plane URL explicitly fixes a 404.
> - `--cli-binary-format raw-in-base64-out` tells the CLI to treat `--payload` as a raw string rather
>   than a base64-encoded blob (the default for blob parameters). Without it the CLI expects the value
>   to already be base64-encoded. Any other client (AWS SDK, `curl`, direct HTTP) sends the JSON body
>   directly with `Content-Type: application/json` and no special encoding is needed.
> - `--content-type application/json` is required for Spring-based runtimes. Without it the AWS CLI
>   omits the `Content-Type` header, AgentCore forwards the request without one, and Spring MVC
>   defaults the missing type to `application/octet-stream` — returning HTTP 415.

### 5. Run the ephemeral integration test

```bash
chmod +x scripts/test-ephemeral.sh
./scripts/test-ephemeral.sh
```

This deploys the CDK stack, runs both test cases against the live runtime, and removes only the
temporary response files. The stack remains deployed afterward.

### 6. Tear down

```bash
cd agentcore/cdk && npx cdk destroy
```

## Configuration

`agentcore/agentcore.json` is the source of truth for how the agent is deployed. Current
configuration:

| Field          | Value                                            |
|----------------|--------------------------------------------------|
| Build          | `Container`                                      |
| Runtime        | Java 21 / Spring Boot 3.4.5 (defined in Dockerfile) |
| Network        | `PUBLIC`                                         |
| Model Provider | `Bedrock`                                        |
| Model          | `global.anthropic.claude-sonnet-4-6` (via `spring.ai.bedrock.converse.chat.options.model`) |
| Agent API      | Spring AI `ChatClient` + `@AgentCoreInvocation`  |

## Documentation

- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [spring-ai-agentcore](https://github.com/spring-ai-community/spring-ai-agentcore)
- [Spring AI — Overview](https://docs.spring.io/spring-ai/reference/)
- [Spring AI — Amazon Bedrock Converse](https://docs.spring.io/spring-ai/reference/api/chat/bedrock-converse.html)
- [AgentCore Runtime Service Contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html)
- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/home.html)
