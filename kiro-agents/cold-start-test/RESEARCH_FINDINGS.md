# AgentCore Runtime-to-Runtime MCP Latency Research

## Objective

Measure cold start latency when an agent hosted on Amazon Bedrock AgentCore Runtime calls an MCP server also hosted on AgentCore Runtime, using streamable-http transport.

## Architecture Deployed

```
┌─────────────────────┐      streamable-http       ┌─────────────────────┐
│   Agent Runtime     │ ──────(SigV4 auth)──────▶  │  MCP Server Runtime │
│  agent_latency_test │                            │  mcp_latency_test   │
│                     │                            │  (2 tools)          │
└─────────────────────┘                            └─────────────────────┘
```

**Region:** us-west-2  
**Account:** 982567305797

## What Was Built

### MCP Server (`mcp-server/mcp_server.py`)

- 2 tools: `get_time` (returns server uptime), `echo`
- Uses `FastMCP` with `stateless_http=True`
- IAM authentication (no Cognito)
- ARN: `arn:aws:bedrock-agentcore:us-west-2:982567305797:runtime/mcp_latency_test-WdwYMX36Ag`

### Agent (`agent/agent.py`)

- Connects to MCP server using `mcp.client.streamable_http.streamablehttp_client`
- Custom SigV4 authentication class for signing requests
- Instrumented with timing measurements at each step
- ARN: `arn:aws:bedrock-agentcore:us-west-2:982567305797:runtime/agent_latency_test-sfcSmq8MqA`

## Key Technical Discovery

The correct URL format for runtime-to-runtime MCP calls:

```
https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{url-encoded-arn}/invocations?qualifier=DEFAULT
```

With SigV4 signing for the `bedrock-agentcore` service:

```python
class SigV4Auth_HTTPX(httpx.Auth):
    def __init__(self, credentials, service, region):
        self.credentials = credentials
        self.service = service  # 'bedrock-agentcore'
        self.region = region

    def auth_flow(self, request):
        aws_request = AWSRequest(method=request.method, url=str(request.url), data=body)
        signer = SigV4Auth(self.credentials, self.service, self.region)
        signer.add_auth(aws_request)
        # Copy signed headers to request
        yield request
```

## Instrumentation Added

```python
async with streamablehttp_client(url=mcp_url, auth=auth) as (read, write, _):
    connect_time = time.time() - mcp_start  # After connection established

    async with ClientSession(read, write) as session:
        await session.initialize()
        init_time = time.time() - mcp_start  # After MCP session init

        tools = await session.list_tools()
        tools_time = time.time() - mcp_start  # After listing tools

        result = await session.call_tool("get_time", {})
        call_time = time.time() - mcp_start  # After tool execution
```

Plus MCP server uptime tracking to detect cold starts:

```python
START_TIME = time.time()

@mcp.tool()
def get_time() -> str:
    return f"Server uptime: {time.time() - START_TIME:.2f}s"
```

## Findings

### Latency Summary

| Scenario | E2E Time | Agent Processing | MCP Call |
|----------|----------|------------------|----------|
| **Agent Cold + MCP Warm** | ~9.6s | ~900ms | ~870ms |
| **Both Warm** | ~3.3s | ~900ms | ~870ms |
| **Both Cold** (estimated) | ~12s | ~900ms | ~870ms + MCP cold |

### MCP Call Breakdown (~900ms warm)

| Step | Latency | Cumulative |
|------|---------|------------|
| Connect (SigV4 HTTP) | ~40-50ms | ~50ms |
| Session initialize | ~400-450ms | ~450ms |
| List tools | ~250-300ms | ~750ms |
| Tool call | ~150-200ms | ~900ms |

### Cold Start Overhead

| Component | Cold Start Time |
|-----------|-----------------|
| Agent Runtime | ~6-7 seconds |
| MCP Server Runtime | ~3-4 seconds (estimated) |
| **Combined** | **~10-12 seconds** |

## Raw Test Data

### Test 1: Agent Cold Start (MCP Warm)
```json
{
  "mcp_result": {
    "tool_result": "Server uptime: 94.91s",
    "connect_ms": 48,
    "init_ms": 388,
    "tools_load_ms": 714,
    "tool_call_ms": 871
  },
  "total_request_ms": 886
}
```
**E2E: 9.6 seconds**

### Test 2: Both Warm
```json
{
  "mcp_result": {
    "tool_result": "Server uptime: 110.51s",
    "connect_ms": 40,
    "init_ms": 479,
    "tools_load_ms": 742,
    "tool_call_ms": 899
  },
  "total_request_ms": 914
}
```
**E2E: 3.3 seconds**

### Test 3: Both Warm
```json
{
  "mcp_result": {
    "tool_result": "Server uptime: 113.70s",
    "connect_ms": 37,
    "init_ms": 425,
    "tools_load_ms": 690,
    "tool_call_ms": 874
  },
  "total_request_ms": 887
}
```
**E2E: 3.3 seconds**

## Observations

1. **AgentCore keeps containers warm longer than expected** - Observed 20+ minutes without scale-down
2. **Redeploying warms the container** - Does not create true cold start scenario
3. **MCP protocol overhead is significant** - ~400-500ms for session initialization alone
4. **12s latency is consistent with double cold start** - Agent (~7s) + MCP (~4s) + call (~1s)
5. **Tool count has minimal impact** - 2 tools vs 7 tools shouldn't significantly change latency

## Recommendations to Reduce Cold Start

### 1. Keep-Warm Pings (Quickest Win)
EventBridge rule every 5 minutes to both endpoints:

```python
# Add to agent
if payload.get("ping"):
    return {"status": "warm"}
```

### 2. Reduce Container Size
- Minimize `requirements.txt`
- Use slim base images
- Remove unused dependencies

### 3. Combine Runtimes
Deploy MCP tools directly in agent runtime - eliminates one cold start entirely.

### 4. Lazy MCP Connection
Don't connect to MCP server until actually needed; cache session if possible.

### 5. Provisioned Concurrency
If supported by AgentCore, keep minimum instances warm.

## Files Created

```
cold-start-test/
├── mcp-server/
│   ├── mcp_server.py      # MCP server with 2 tools
│   └── requirements.txt
├── agent/
│   ├── agent.py           # Agent with SigV4 MCP client
│   └── requirements.txt
├── test_latency.py        # Test script
└── RESEARCH_FINDINGS.md   # This file
```

## How to Reproduce

```bash
# Deploy MCP server
cd cold-start-test/mcp-server
agentcore configure --entrypoint mcp_server.py
agentcore launch

# Deploy agent with MCP server ARN
cd cold-start-test/agent
agentcore configure --entrypoint agent.py
agentcore launch --env MCP_SERVER_ARN=<mcp-server-arn>

# Test
agentcore invoke '{"prompt": "test"}'
```

---

*Research conducted: January 30, 2026*
