# Self-Managed Agents: Agentic Architectures on AWS

## Overview

**Self-managed agents** refers to AI agents where you own the operational concerns—compute provisioning, lifecycle management, scaling, and critically, the security and identity layer. Unlike fully managed platforms such as Amazon Bedrock AgentCore, there is no platform handling these for you. You bring your own agent framework (Strands, LangGraph, CrewAI, custom, etc.) and take responsibility for how agents authenticate, what they're authorized to do, and how that's enforced.

This is a deliberate choice, not a limitation. The "self-managed" label describes the operational model, not the agent's intelligence or design.

Typical self-managed deployment targets on AWS:

- **Amazon ECS (Fargate or EC2 launch type)**: Containerized agents as long-running services or tasks
- **Amazon EKS**: Kubernetes-native deployments—Deployments, DaemonSets, StatefulSets, or custom Operators
- **Amazon EC2**: Agents running directly on instances, useful for specialized hardware (GPUs, Inferentia) or OS-level access
- **AWS Lambda**: Serverless agents where the compute is managed by AWS, but the security model—authentication, authorization, token handling, and inter-agent trust—is entirely hand-built by you. Lambda also has a hard 15-minute execution limit per invocation and no native session isolation between invocations, which shapes the kinds of agent tasks it suits well.

The key distinction with Lambda is worth calling out explicitly: Lambda removes infrastructure management (no servers to provision or scale), but it does not remove security management. When you run agents on Lambda outside of AgentCore, you are responsible for building the identity and access control layer that [AgentCore Identity](https://aws.amazon.com/bedrock/agentcore/) provides out of the box—OAuth 2.0 flows, token validation, scoped permissions per agent, and audit trails for agent actions.

Beyond security, Lambda's runtime constraints are a meaningful design input. AgentCore supports agent sessions up to 8 hours with session-level isolation—each session gets its own context, memory scope, and identity boundary. Lambda invocations are capped at 15 minutes and are stateless by default; there is no built-in session boundary between invocations. This doesn't prevent you from running agents on Lambda, but it does mean you design differently: tasks must complete within a single invocation or be decomposed across multiple, and session continuity (if needed) has to be reconstructed from external state (DynamoDB, ElastiCache, S3) on each invocation.

### When to Choose Self-Managed Over AgentCore

[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) handles the infrastructure and security platform for you—runtime, scaling, patching, observability, and identity. Self-managed makes sense when you need control that a managed platform can't provide, or when you're already invested in your own stack:

**Choose self-managed when:**

1. **You already have ECS/EKS clusters** — your team has the operational expertise, CI/CD pipelines, and monitoring already in place. Running agents alongside existing workloads is lower friction than adopting a new platform.

2. **You need hardware control** — GPUs, AWS Inferentia, or Trainium instances for model inference; custom container runtimes; or kernel-level access (cgroups, syscalls) that serverless runtimes don't expose.

3. **Long-running, stateful processes** — agents that maintain in-memory state, hold persistent connections (WebSockets, gRPC streams), or run continuously rather than responding to discrete invocations.

4. **Kubernetes-native patterns are core to your architecture** — DaemonSets for node-level agents, custom Operators with CRDs, service mesh integration (Istio, Linkerd), or multi-cluster federation.

5. **Hybrid or multi-cloud requirements** — agents that must run consistently across AWS, on-premises, and other clouds; Kubernetes portability is a hard requirement.

6. **Cost optimization at scale** — high-volume workloads where you want to leverage Spot instances, Reserved Instances, or custom bin-packing; predictable traffic patterns that benefit from reserved capacity.

7. **Compliance or air-gapped environments** — no internet connectivity, custom encryption/KMS, specific audit log formats, or FIPS-compliant hardened environments.

8. **You're running agents on Lambda and need fine-grained control** — Lambda is a valid platform for agents, particularly for discrete, short-lived tasks. The trade-offs to design around are:
   - **15-minute execution limit**: A single Lambda invocation can run for at most 15 minutes. Agents with long reasoning chains, multi-step tool use, or tasks that take longer must be decomposed—either into chained invocations via Step Functions, or by externalizing state and resuming across invocations.
   - **No built-in session isolation**: AgentCore provides session-level isolation—each agent session has its own context boundary, memory scope, and identity. Lambda has no equivalent; every invocation is stateless and isolated from others by default. If your agent needs session continuity (conversation history, accumulated context, mid-task state), you build and manage that yourself using DynamoDB, ElastiCache, or S3.
   - **Custom security model**: Lambda removes compute management but not security management. Auth flows, token validation, and inter-agent trust are yours to implement—AgentCore Identity handles this on the managed platform.

   Lambda is a strong fit for agents doing well-scoped, event-driven tasks that complete within 15 minutes and don't require session continuity. For longer-running or session-aware agents, ECS/EKS or AgentCore are better fits.

**Choose AgentCore when:**

- You want to focus on agent logic, not infrastructure or security plumbing
- You need built-in identity management (AgentCore Identity), memory, code execution, and observability out of the box
- You're starting fresh without legacy infrastructure constraints
- Faster time-to-market matters more than control over the security model

**Hybrid approach:**

Many teams run both. AgentCore for agents where the managed security and runtime are a good fit; self-managed ECS/EKS/Lambda for agents that need deep infrastructure access, custom identity flows, or already live alongside existing workloads.

---

## Pattern Selection Guide

The patterns in this guide cover agent deployments across ECS, EKS, EC2, and Lambda. For ECS/EKS/EC2, "self-managed" means owning the compute and runtime. For Lambda (Patterns 1 and 6), "self-managed" means owning the security model—authentication, authorization, and inter-agent trust that AgentCore Identity would otherwise provide.

| Use Case | Recommended Patterns | Why |
|----------|---------------------|-----|
| Existing ECS/EKS investment | Pattern 2 (ECS Long-Running), Pattern 3 (EKS DaemonSets), Pattern 4 (EKS Operators) | Leverage existing container orchestration and operational expertise |
| Hardware control (GPU/Inferentia) | Pattern 3 (EKS DaemonSets), Pattern 2 (ECS on EC2) | Direct node access, custom instance types, specialized scheduling |
| Hybrid/Multi-Cloud | Pattern 4 (EKS Operators), Pattern 9 (MCP on EKS), Pattern 10 (A2A on EKS) | Kubernetes portability, standardized protocols, cloud-agnostic patterns |
| Cost optimization at scale | Pattern 7 (ECS Auto-Scaling), Pattern 2 (ECS on Spot) | Custom scaling algorithms, Spot instance support, reserved capacity |
| Legacy system integration | Pattern 2 (ECS Long-Running), Pattern 9 (MCP on EKS) | Custom protocols, persistent connections, standardized integration layer |
| Kubernetes-native patterns | Pattern 3 (EKS DaemonSets), Pattern 4 (EKS Operators), Pattern 10 (A2A on EKS) | CRDs, operators, native Kubernetes resources and APIs |
| Compliance/air-gapped | Pattern 8 (Cross-Account Networks), Pattern 3 (EKS DaemonSets) | Air-gapped deployments, custom encryption, multi-account isolation |
| Custom security/identity model on Lambda | Pattern 1 (Lambda Event-Driven), Pattern 6 (Lambda + Step Functions) | Full control over auth flows, token validation, and inter-agent trust policies |
| Distributed coordination | Pattern 5 (Multi-Agent Choreography), Pattern 10 (A2A Communication) | Event-driven coordination, peer-to-peer communication, no central orchestrator |
| Complex workflows | Pattern 6 (Lambda + Step Functions) | Visual workflow definition, state management, built-in error handling |

**Pattern Combinations:**

Real-world implementations often combine multiple patterns:

- **ECS + Event Mesh**: Pattern 2 (ECS Long-Running) + Pattern 5 (Event Mesh) — ECS agents for stateful processing, EventBridge for async coordination between agent pools

- **Kubernetes-Native Platform**: Pattern 3 (DaemonSets) + Pattern 4 (Operators) + Pattern 9 (MCP) — DaemonSets for node-level agents, Operators for resource management, MCP for AI model integration

- **Multi-Agent Collaboration on EKS**: Pattern 9 (MCP) + Pattern 10 (A2A) + Pattern 5 (Event Mesh) — MCP for capability exposure, A2A for direct agent communication, EventBridge for async coordination

- **Enterprise Multi-Account**: Pattern 8 (Cross-Account) + Pattern 2 (ECS) — central ECS orchestration with distributed execution across organizational boundaries

---

## Agentic Patterns on AWS

The patterns in this guide span ECS, EKS, EC2, and Lambda. For ECS/EKS/EC2 patterns, self-managed means owning the compute and runtime. For Lambda patterns (1 and 6), self-managed means owning the security model—you build the authentication, authorization, and inter-agent trust layer that AgentCore Identity provides on the managed platform.

### Pattern 1: Lambda Event-Driven Agents

**Characteristics**: Stateless, event-triggered agents that react to system events and execute discrete tasks.

**Runtime Constraints vs AgentCore**:

| | Lambda (self-managed) | AgentCore |
|---|---|---|
| Max execution time | 15 minutes per invocation | 8 hours per session |
| Session isolation | None built-in — stateless by default | Native session-level isolation with scoped context and memory |
| Security/identity | Hand-built (IAM + custom auth) | AgentCore Identity (OAuth 2.0, token validation, audit) |
| Session continuity | Reconstructed from external state (DynamoDB, ElastiCache) | Managed by platform |

Lambda agents work well for tasks that fit within a single invocation. For agents that need to reason across multiple steps over a longer horizon, or maintain isolated session context per user/conversation, you either chain invocations through Step Functions (Pattern 6) with externalized state, or move to ECS/EKS for persistent processes, or use AgentCore for the managed session model.

**Architecture**:
```
EventBridge/SNS/SQS → Lambda Agent → DynamoDB (state) → Target Service
                           ↓
                    CloudWatch Logs/Metrics
```

**Implementation**:
- Lambda functions subscribe to event streams (EventBridge, SQS, Kinesis)
- Each invocation represents an agent "awakening" to process an event
- State stored in DynamoDB or S3 between invocations
- Decision logic embedded in function code (rules engine, ML inference)

**Use Cases**:
- Auto-remediation agents (security group violations, cost anomalies)
- Data transformation pipelines with intelligent routing
- Approval workflow agents with policy-based decision making
- Resource lifecycle managers (cleanup, archival, optimization)

**Example**: A cost optimization agent that analyzes CloudWatch metrics, identifies underutilized RDS instances, snapshots them, and scales down—all triggered by scheduled EventBridge rules.

---

### Pattern 2: ECS Long-Running Agent Tasks

**Characteristics**: Persistent agents running as ECS tasks that maintain state and continuously monitor systems.

**Architecture**:
```
ECS Cluster (Fargate/EC2)
  └── Agent Task(s)
       ├── Polling Loop / WebSocket Listener
       ├── Local State Cache (Redis/In-Memory)
       ├── Decision Engine
       └── Action Executors → AWS APIs
```

**Implementation**:
- Agents run as containerized services with restart policies
- Use AWS SDK to interact with control plane (EC2, Auto Scaling, etc.)
- Maintain internal state for decision context
- Can implement sophisticated algorithms (gradient descent for resource allocation)

**Use Cases**:
- Continuous deployment agents monitoring Git repos and triggering pipelines
- Chaos engineering agents injecting faults based on schedules
- Capacity planning agents adjusting cluster sizes
- Security compliance agents scanning and remediating configuration drift

**Example**: A deployment agent that watches an S3 bucket for new artifacts, performs smoke tests, gradually shifts traffic using Application Load Balancer weights, and rolls back on anomaly detection.

---

### Pattern 3: EKS Agent DaemonSets

**Characteristics**: Kubernetes-native agents running on every node via DaemonSets, providing node-level intelligence.

**Architecture**:
```
EKS Cluster
  ├── Node 1 → Agent DaemonSet Pod
  ├── Node 2 → Agent DaemonSet Pod
  └── Node N → Agent DaemonSet Pod
           ↓
    Kubernetes API (watches, patches)
    Host System (cgroups, syscalls)
```

**Implementation**:
- DaemonSet ensures one agent pod per node
- Agents use Kubernetes client libraries to watch resources
- Access to node-level metrics via hostPath volumes
- Can modify pod specs, node labels, or trigger evictions

**Use Cases**:
- Log shipping agents with intelligent batching/compression
- Security agents scanning containers for vulnerabilities
- Resource optimization agents adjusting QoS classes
- Network policy enforcement agents

**Example**: A node resource balancer that monitors CPU/memory pressure, communicates with other node agents via custom CRDs, and cooperatively rebalances pods across the cluster using taints and tolerations.

---

### Pattern 4: EKS Operator-Based Agents

**Characteristics**: Custom Kubernetes operators that extend the API with domain-specific resources and reconciliation loops.

**Architecture**:
```
Custom Resource Definition (CRD)
         ↓
   Custom Resource
         ↓
Operator Controller (Agent)
  ├── Watch Loop
  ├── Reconciliation Logic
  └── Status Updates
         ↓
   Kubernetes Resources
```

**Implementation**:
- Define CRDs representing business concepts (e.g., `Database`, `Pipeline`)
- Operator watches for CRD changes and reconciles desired vs actual state
- Implements control loops with exponential backoff
- Updates resource status to reflect operational state

**Use Cases**:
- Database operators provisioning RDS instances from Kubernetes
- Certificate rotation agents managing TLS secrets
- Backup operators coordinating snapshot schedules
- Multi-cluster deployment agents

**Example**: A `DatabaseMigration` operator that watches for new migration CRDs, provisions temporary ECS tasks to run Flyway, monitors completion, and updates status fields—all while handling retries and failures gracefully.

---

### Pattern 5: Multi-Agent Choreography via Event Mesh

**Characteristics**: Multiple specialized agents coordinate through asynchronous messaging without central orchestration.

**Architecture**:
```
Agent A (Lambda) → EventBridge → Agent B (ECS Task)
                        ↓
                   Agent C (EKS Pod)
                        ↓
                   Agent D (Lambda)
```

**Implementation**:
- Each agent publishes domain events to EventBridge
- Agents subscribe to relevant event patterns
- No single agent has complete workflow knowledge
- Saga pattern for distributed transactions

**Use Cases**:
- Order fulfillment with inventory, payment, and shipping agents
- Data pipeline with ingestion, transformation, and publishing agents
- Incident response with detection, triage, and remediation agents

**Example**: A CI/CD system where a code-push agent (Lambda) emits a `CodeCommitted` event, triggering a build agent (ECS), which emits `BuildCompleted`, triggering a test agent (EKS), which emits `TestsPassed`, triggering a deploy agent (Lambda)—each handling failures independently with compensating actions.

---

### Pattern 6: Lambda Agents with Step Functions State Machines

**Characteristics**: Lambda agents coordinated by Step Functions for complex, multi-step workflows requiring visibility.

**Architecture**:
```
Step Functions State Machine
  ├── Agent Task (Lambda) - Analyze
  ├── Choice State (Decision Point)
  ├── Agent Task (Lambda) - Act
  └── Parallel State
       ├── Agent Task (Lambda) - Notify
       └── Agent Task (Lambda) - Log
```

**Implementation**:
- Step Functions provides workflow definition and state management
- Each Lambda is an agent executing a specific capability
- Agents remain stateless; Step Functions maintains workflow state
- Supports retries, error handling, and long-running processes

**Use Cases**:
- Data processing pipelines with conditional branches
- Approval workflows with human-in-the-loop
- Multi-stage deployment with rollback capabilities
- Compliance validation chains

**Example**: A data quality agent workflow where extraction agents pull data, validation agents check schema/quality, transformation agents clean data, and publishing agents write to data lake—with Step Functions managing state transitions and capturing provenance.

---

### Pattern 7: ECS Service Auto-Scaling Agents

**Characteristics**: Agents that implement custom auto-scaling logic beyond built-in AWS capabilities.

**Architecture**:
```
CloudWatch Metrics → Lambda Agent
                          ↓
                  Decision Algorithm
                    (ML Model/Rules)
                          ↓
                ECS UpdateService API
```

**Implementation**:
- CloudWatch Alarms or EventBridge rules trigger Lambda
- Agent fetches historical metrics, current task count, and cluster capacity
- Applies predictive algorithms or reinforcement learning
- Calls ECS APIs to update desired task count

**Use Cases**:
- Traffic prediction for preemptive scaling
- Cost-optimized scaling balancing performance and budget
- Workload-aware scaling (queue depth, response time)

**Example**: A predictive scaling agent that analyzes week-over-week traffic patterns using a time-series model, scales ECS services 15 minutes before anticipated load spikes, and adjusts aggressively during anomalies.

---

### Pattern 8: Cross-Account Agent Networks

**Characteristics**: Agents operating across multiple AWS accounts for centralized management of distributed infrastructure.

**Architecture**:
```
Management Account
  └── Orchestrator Agent (ECS)
       ├── AssumeRole → Account A → Worker Agent
       ├── AssumeRole → Account B → Worker Agent
       └── AssumeRole → Account C → Worker Agent
```

**Implementation**:
- Central agent in hub account assumes roles in spoke accounts
- Worker agents in each account execute localized tasks
- EventBridge event buses bridged across accounts
- Shared artifact storage via S3 cross-account access

**Use Cases**:
- Multi-account security posture management
- Centralized backup orchestration
- Cross-account cost optimization
- Compliance reporting aggregation

**Example**: A security remediation agent in a central account that receives GuardDuty findings from all accounts via EventBridge, assumes roles to inspect resources, and automatically isolates compromised instances by modifying security groups.

---

### Pattern 9: MCP (Model Context Protocol) Agents on EKS

**Characteristics**: Self-managed agents that expose MCP servers to provide AI models with secure, standardized access to infrastructure resources and capabilities.

**What is MCP?**

Model Context Protocol (MCP) is an open protocol that enables AI models to securely connect to external data sources and tools. In the context of self-managed agents, MCP servers run as Kubernetes services, exposing infrastructure capabilities through a standardized interface that AI systems can discover and invoke.

**Architecture**:
```
EKS Cluster
  ├── MCP Server Pods (Deployment)
  │    ├── Resource Endpoints
  │    ├── Tool Endpoints
  │    └── Prompt Templates
  │
  ├── Agent Pods (consume MCP)
  │    └── MCP Client → calls MCP Server
  │
  └── Service Mesh (mTLS, AuthN/AuthZ)
```

**Implementation**:

MCP servers expose three types of capabilities:
1. **Resources**: Read-only access to data (metrics, logs, configurations)
2. **Tools**: Actions the agent can perform (scale, deploy, restart)
3. **Prompts**: Predefined templates for common operations

**Example MCP Server Deployment**:
```python
# mcp_server.py - Runs as a Kubernetes Deployment
from mcp import MCPServer, Resource, Tool
from kubernetes import client, config
import boto3

config.load_incluster_config()
v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

# Initialize MCP server
server = MCPServer(name="k8s-infrastructure-mcp")

# Expose Kubernetes resources via MCP
@server.resource("pods/{namespace}")
def get_pods(namespace: str):
    """List pods in a namespace"""
    pods = v1.list_namespaced_pod(namespace)
    return {
        "pods": [
            {
                "name": p.metadata.name,
                "status": p.status.phase,
                "containers": [c.name for c in p.spec.containers]
            }
            for p in pods.items
        ]
    }

@server.resource("deployments/{namespace}/{name}/metrics")
def get_deployment_metrics(namespace: str, name: str):
    """Get metrics for a deployment"""
    deployment = apps_v1.read_namespaced_deployment(name, namespace)
    return {
        "replicas": deployment.status.replicas,
        "ready_replicas": deployment.status.ready_replicas,
        "updated_replicas": deployment.status.updated_replicas
    }

# Expose infrastructure actions as MCP tools
@server.tool("scale_deployment")
def scale_deployment(namespace: str, name: str, replicas: int):
    """Scale a Kubernetes deployment"""
    apps_v1.patch_namespaced_deployment_scale(
        name=name,
        namespace=namespace,
        body={"spec": {"replicas": replicas}}
    )
    return {"status": "success", "replicas": replicas}

@server.tool("restart_deployment")
def restart_deployment(namespace: str, name: str):
    """Restart a deployment by updating annotations"""
    from datetime import datetime
    patch = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": datetime.utcnow().isoformat()
                    }
                }
            }
        }
    }
    apps_v1.patch_namespaced_deployment(name, namespace, body=patch)
    return {"status": "restarted", "deployment": name}

# Prompt templates for common operations
@server.prompt("troubleshoot_pod")
def troubleshoot_prompt(pod_name: str, namespace: str):
    """Generate troubleshooting prompt for a failing pod"""
    return f"""
    Investigate why pod {pod_name} in namespace {namespace} is failing.
    Steps:
    1. Check pod status and events
    2. Review container logs
    3. Verify resource limits
    4. Check network policies
    5. Provide diagnosis and remediation steps
    """

if __name__ == "__main__":
    server.run(host="0.0.0.0", port=8080)
```

**Kubernetes Deployment Manifest**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k8s-mcp-server
  namespace: agent-system
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      serviceAccountName: mcp-server-sa
      containers:
      - name: mcp-server
        image: my-registry/k8s-mcp-server:latest
        ports:
        - containerPort: 8080
        env:
        - name: MCP_SERVER_NAME
          value: "k8s-infrastructure"
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-server
  namespace: agent-system
spec:
  selector:
    app: mcp-server
  ports:
  - port: 8080
    targetPort: 8080
```

**Agent Consuming MCP Server**:
```python
# agent_pod.py - Self-managed agent using MCP
from mcp import MCPClient
import asyncio

async def autonomous_scaling_agent():
    """Agent that uses MCP to monitor and scale deployments"""
    
    # Connect to MCP server
    client = MCPClient("http://mcp-server.agent-system.svc.cluster.local:8080")
    
    while True:
        # Query deployment metrics via MCP resource
        metrics = await client.get_resource(
            "deployments/production/api-service/metrics"
        )
        
        current_replicas = metrics["replicas"]
        ready_replicas = metrics["ready_replicas"]
        
        # Decision logic
        if ready_replicas < current_replicas:
            print("Unhealthy deployment detected, investigating...")
            
            # Use MCP prompt for troubleshooting
            prompt = await client.get_prompt(
                "troubleshoot_deployment",
                name="api-service",
                namespace="production"
            )
            # Send to LLM or follow checklist
            
        elif current_replicas < 5 and is_high_traffic_time():
            # Scale up using MCP tool
            await client.call_tool(
                "scale_deployment",
                namespace="production",
                name="api-service",
                replicas=10
            )
            print("Scaled up for high traffic period")
        
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(autonomous_scaling_agent())
```

**Use Cases**:
- **Multi-tenant infrastructure management**: MCP servers per tenant namespace, agents with scoped access
- **AI-powered operations**: LLM-based agents use MCP to safely interact with infrastructure
- **Centralized capability discovery**: Agents discover available infrastructure actions dynamically
- **Audit and compliance**: All infrastructure access logged through MCP layer
- **Cross-cluster orchestration**: MCP servers in different clusters, coordinating agents

---

### Pattern 10: Agent-to-Agent (A2A) Communication on EKS

**Characteristics**: Multiple specialized self-managed agents coordinate through direct communication protocols to accomplish distributed tasks without central orchestration.

**Architecture**:
```
EKS Cluster
  ├── Monitoring Agent Pods
  │    └── Watches metrics, detects anomalies
  │         ↓ (gRPC/HTTP/Message Queue)
  ├── Analysis Agent Pods
  │    └── Receives data, determines root cause
  │         ↓ (gRPC/HTTP/Message Queue)
  ├── Remediation Agent Pods
  │    └── Executes fixes based on analysis
  │         ↓ (gRPC/HTTP/Message Queue)
  └── Notification Agent Pods
       └── Alerts humans if needed
```

**Implementation Patterns**:

**A2A Pattern 1: gRPC-Based Direct Communication**
```python
# agent_protocol.proto
syntax = "proto3";

service AgentCommunication {
  rpc RequestAction(ActionRequest) returns (ActionResponse);
  rpc ReportStatus(StatusReport) returns (Acknowledgment);
  rpc QueryCapabilities(Empty) returns (CapabilityList);
}

message ActionRequest {
  string agent_id = 1;
  string action_type = 2;
  map<string, string> parameters = 3;
  int32 priority = 4;
}

message ActionResponse {
  string request_id = 1;
  bool accepted = 2;
  string status = 3;
  map<string, string> result = 4;
}
```

```python
# monitoring_agent.py
import grpc
from agent_protocol_pb2 import ActionRequest
from agent_protocol_pb2_grpc import AgentCommunicationStub

class MonitoringAgent:
    def __init__(self):
        self.analysis_agent_channel = grpc.insecure_channel(
            'analysis-agent.agent-system.svc.cluster.local:50051'
        )
        self.analysis_stub = AgentCommunicationStub(self.analysis_agent_channel)
    
    async def detect_anomaly(self, metric_data):
        """When anomaly detected, request analysis from analysis agent"""
        request = ActionRequest(
            agent_id="monitoring-agent-001",
            action_type="analyze_anomaly",
            parameters={
                "metric": metric_data["name"],
                "value": str(metric_data["value"]),
                "threshold": str(metric_data["threshold"]),
                "namespace": metric_data["namespace"]
            },
            priority=5
        )
        
        response = self.analysis_stub.RequestAction(request)
        return response
```

```python
# analysis_agent.py
import grpc
from concurrent import futures
from agent_protocol_pb2 import ActionResponse
from agent_protocol_pb2_grpc import AgentCommunicationServicer

class AnalysisAgent(AgentCommunicationServicer):
    def __init__(self):
        self.remediation_agent_channel = grpc.insecure_channel(
            'remediation-agent.agent-system.svc.cluster.local:50051'
        )
        self.remediation_stub = AgentCommunicationStub(
            self.remediation_agent_channel
        )
    
    def RequestAction(self, request, context):
        """Receive action request from other agents"""
        if request.action_type == "analyze_anomaly":
            # Perform analysis
            root_cause = self.analyze_metrics(request.parameters)
            
            # Request remediation if needed
            if root_cause["severity"] == "high":
                self.request_remediation(root_cause)
            
            return ActionResponse(
                request_id=request.agent_id,
                accepted=True,
                status="analyzed",
                result=root_cause
            )
    
    def request_remediation(self, analysis):
        """Ask remediation agent to fix the issue"""
        request = ActionRequest(
            agent_id="analysis-agent-001",
            action_type="remediate",
            parameters=analysis,
            priority=analysis["severity_score"]
        )
        self.remediation_stub.RequestAction(request)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_AgentCommunicationServicer_to_server(AnalysisAgent(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()
```

**A2A Pattern 2: Message Queue-Based Choreography**
```python
# Using NATS for agent communication
import nats
import asyncio
import json

class DeploymentAgent:
    async def run(self):
        nc = await nats.connect("nats://nats.agent-system.svc.cluster.local:4222")
        
        # Subscribe to deployment requests
        async def deployment_handler(msg):
            data = json.loads(msg.data.decode())
            result = await self.deploy(data)
            
            # Publish completion event for other agents
            await nc.publish(
                "agent.deployment.completed",
                json.dumps({
                    "agent_id": "deployment-agent-001",
                    "deployment": data["name"],
                    "status": result["status"],
                    "version": data["version"]
                }).encode()
            )
        
        await nc.subscribe("agent.deployment.requested", cb=deployment_handler)
        
        # Keep running
        while True:
            await asyncio.sleep(1)

class TestAgent:
    async def run(self):
        nc = await nats.connect("nats://nats.agent-system.svc.cluster.local:4222")
        
        # Listen for deployment completions
        async def test_handler(msg):
            data = json.loads(msg.data.decode())
            
            # Run tests against new deployment
            test_results = await self.run_tests(data["deployment"])
            
            # Publish test results
            await nc.publish(
                f"agent.test.completed",
                json.dumps({
                    "agent_id": "test-agent-001",
                    "deployment": data["deployment"],
                    "passed": test_results["passed"],
                    "failures": test_results["failures"]
                }).encode()
            )
        
        await nc.subscribe("agent.deployment.completed", cb=test_handler)
        
        while True:
            await asyncio.sleep(1)
```

**A2A Pattern 3: Service Mesh-Enabled Communication**
```yaml
# Using Istio for secure agent-to-agent communication
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: agent-mtls
  namespace: agent-system
spec:
  mtls:
    mode: STRICT
---
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: agent-communication-policy
  namespace: agent-system
spec:
  selector:
    matchLabels:
      app: remediation-agent
  action: ALLOW
  rules:
  - from:
    - source:
        principals: ["cluster.local/ns/agent-system/sa/analysis-agent"]
    to:
    - operation:
        methods: ["POST"]
        paths: ["/v1/remediate"]
```

**A2A Pattern 4: Consensus-Based Coordination**
```python
# Agents coordinate using etcd for consensus
import etcd3
import json
import time

class ScalingAgent:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.etcd = etcd3.client(
            host='etcd.agent-system.svc.cluster.local'
        )
    
    async def coordinate_scaling(self, service_name, desired_replicas):
        """
        Multiple scaling agents coordinate to avoid conflicts
        Uses distributed lock to ensure only one scales at a time
        """
        lock_key = f"/locks/scaling/{service_name}"
        
        # Try to acquire lock
        lock = self.etcd.lock(lock_key, ttl=30)
        if lock.acquire(blocking=False):
            try:
                # Check if another agent already scaled
                current_state = self.get_scaling_state(service_name)
                
                if current_state["last_scaled_at"] > (time.time() - 300):
                    print(f"Recently scaled by {current_state['agent_id']}, skipping")
                    return
                
                # Perform scaling
                self.scale_deployment(service_name, desired_replicas)
                
                # Update shared state
                self.etcd.put(
                    f"/state/scaling/{service_name}",
                    json.dumps({
                        "agent_id": self.agent_id,
                        "replicas": desired_replicas,
                        "last_scaled_at": time.time()
                    })
                )
            finally:
                lock.release()
        else:
            print(f"Another agent is scaling {service_name}, deferring")
```

**Use Cases**:

**Distributed Incident Response**
- Monitoring agents detect issues → Analysis agents diagnose → Remediation agents fix → Notification agents alert humans
- Each agent type specialized, communicates findings to next in chain
- Parallel processing: multiple incidents handled simultaneously by agent pools

**Collaborative Resource Optimization**
- CPU agents monitor compute usage → Memory agents track allocation → Network agents observe bandwidth
- Agents share insights via A2A communication
- Consensus on optimization actions to avoid conflicts

**Self-Healing Deployment Pipeline**
- Build agent completes → Test agent validates → Security scan agent checks vulnerabilities → Deploy agent rolls out
- Each agent reports progress/failures to others
- Rollback coordinated if any agent reports failure

**Multi-Cluster Coordination**
- Agents in cluster A communicate with agents in cluster B via federation
- Cross-cluster workload balancing
- Disaster recovery coordination

**Benefits of A2A on EKS**:
- **Decentralization**: No single point of failure
- **Specialization**: Each agent has narrow responsibility
- **Scalability**: Add more agent pods as needed
- **Resilience**: Agent failures don't cascade
- **Flexibility**: Easy to add new agent types

---

## Design Considerations


- **Stateless Agents (Lambda)**: Use DynamoDB, S3, or Parameter Store for persistence
- **Stateful Agents (ECS/EKS)**: In-memory state with periodic snapshots, or external databases
- **Distributed State**: Consider event sourcing or CQRS patterns

### Error Handling
- Implement exponential backoff with jitter
- Use dead-letter queues for unprocessable events
- Emit metrics for failures and set up alarms
- Distinguish transient vs permanent failures

### Observability
- Structured logging with correlation IDs across agent interactions
- Custom CloudWatch metrics for agent-specific KPIs
- Distributed tracing with X-Ray for multi-agent flows
- Dashboards showing agent health, decision outcomes, and actions taken

### Security
- Principle of least privilege for IAM roles
- Agent authentication via IAM roles, not long-lived credentials
- Encrypt state at rest and in transit
- Audit logs for all agent actions

### Testing
- Unit tests for decision logic
- Integration tests with LocalStack or AWS mocks
- Chaos engineering to validate resilience
- Shadow mode deployments for ML-based agents

---

## Anti-Patterns to Avoid

❌ **Chatty Agents**: Agents making excessive API calls without batching or caching  
❌ **God Agents**: Single agent with too many responsibilities; prefer specialized agents  
❌ **Hidden State**: Agent state not visible to operators, making debugging impossible  
❌ **Unbounded Autonomy**: Agents without circuit breakers or human approval gates for critical actions  
❌ **Tight Coupling**: Agents depending on implementation details of other agents rather than contracts  

---

## Getting Started

1. **Pick your compute target**: ECS Fargate for simplicity, ECS on EC2 for hardware control, EKS for Kubernetes-native patterns
2. **Containerize your agent**: Package your agent framework (Strands, LangGraph, custom) as a Docker image with a clear entrypoint
3. **Add observability first**: Structured logging, CloudWatch metrics, and X-Ray tracing before you add complexity
4. **Start with a single agent service**: One ECS task or EKS Deployment doing a well-defined job
5. **Introduce coordination**: EventBridge for async choreography, gRPC/NATS for direct A2A communication, or CRDs for Kubernetes-native state
6. **Iterate on intelligence**: Start with rules-based logic, then introduce LLM calls or ML models as the agent matures

---

## References

- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Amazon ECS Task Definitions](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definitions.html)
- [Kubernetes Operators](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)
- [EventBridge Event Patterns](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns.html)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- [The Reactive Manifesto](https://www.reactivemanifesto.org/)

---

## Existing Patterns and Reference Implementations

### EKS/ECS Patterns

#### 1. Scalable Model Inference and Agentic AI on Amazon EKS

**Repository**: [AWS Solutions Guidance](https://aws-solutions-library-samples.github.io/compute/scalabale-model-inference-and-agentic-ai-on-amazon-eks.html)

**Pattern Type**: Pattern 4 (EKS Operators), Pattern 9 (MCP on EKS), Pattern 10 (A2A Communication)

**Overview**: 
A comprehensive, production-ready architecture for deploying Large Language Models (LLMs) and agentic AI applications on Amazon EKS. This implementation demonstrates enterprise-grade patterns for self-managed agents with intelligent resource allocation and unified model inference.

**Key Components**:
- **Multi-Agent Architecture**: Orchestrator agent, RAG agent, Evaluation agent, and Web Search agent working collaboratively
- **Compute Optimization**: 
  - AWS Graviton processors for cost-effective CPU-based core services
  - NVIDIA GPU and AWS Inferentia instances for accelerated inference
  - Karpenter auto-scaler for dynamic resource provisioning
- **Model Hosting Services**:
  - vLLM for high-throughput GPU/Inferentia inference
  - LiteLLM as unified API gateway proxy for model management
  - KubeRay cluster for distributed embedding processes
- **Knowledge Management**:
  - Amazon OpenSearch for vector database operations
  - RAG capabilities with automatic knowledge base validation
  - Dynamic embedding pipeline with llamacpp framework
- **Observability Stack**:
  - Strands Agent SDK with built-in OpenTelemetry tracing
  - LangFuse for agent activity visualization
  - Amazon Managed Service for Prometheus (AMP)
  - Amazon Managed Service for Grafana (AMG)

**Agent Workflows**:

1. **Orchestration Flow**: 
   - User requests → Orchestrator agent (Strands SDK) → Reasoning models (via LiteLLM/vLLM)
   - Orchestrator analyzes requests and determines appropriate workflow and tools

2. **Knowledge Validation**:
   - RAG agent verifies knowledge base validity
   - Initiates embedding process when updates needed
   - KubeRay cluster handles distributed embedding with dynamic scaling

3. **Quality Assurance Loop**:
   - Evaluation agent uses Amazon Bedrock models
   - Implements RAGAS metrics for response quality assessment
   - Provides relevancy scores for decision-making

4. **Web Search Fallback**:
   - Triggered when RAG responses score below threshold
   - Retrieves Tavily web search API tool from MCP server
   - Performs dynamic queries for supplementary information

**Architecture Highlights**:
- **Multi-AZ Deployment**: 3 Availability Zones for high availability
- **Security**: IAM-based RBAC, VPC endpoints, encryption at rest and in transit
- **Cost**: ~$447/month for default configuration in us-east-1
- **Deployment Time**: 35-45 minutes automated setup

**Use Cases**:
- Medical knowledge query systems with document analysis
- Intelligent document processing (IDP) with RAG
- Multi-agent customer service automation
- Research and development environments requiring flexible AI infrastructure

**Technologies**: Strands Agent SDK, Kubernetes, Karpenter, vLLM, LiteLLM, KubeRay, OpenSearch, LangFuse, Prometheus, Grafana

---

#### 2. MCPify REST APIs with Amazon Bedrock AgentCore Gateway on EKS

**Repository**: [sample-mcpify-rest-apis-with-agentcore](./sample-mcpify-rest-apis-with-agentcore/)

**Pattern Type**: Pattern 9 (MCP on EKS), Pattern 8 (Cross-Account Networks)

**Overview**:
A complete sample demonstrating how to transform existing REST APIs into AI agent tools using Amazon Bedrock AgentCore Gateway and the Model Context Protocol (MCP). Shows the full architecture: Amazon QuickSuite → AgentCore Gateway → EKS Application → DynamoDB.

**Key Components**:
- **Flask Retail API**: 12 REST endpoints (orders, products, customers, purchases, analytics) running on EKS
- **AgentCore Gateway Integration**: Converts REST API to MCP-compatible tools via OpenAPI specification
- **Terraform Infrastructure**: EKS cluster, VPC, DynamoDB with customer-managed KMS encryption, IRSA
- **Kubernetes Deployment**: Hardened security contexts (non-root, read-only FS, dropped capabilities)
- **OAuth 2.0 Authentication**: Amazon Cognito integration for secure gateway access
- **QuickSuite Integration**: Natural language interactions with retail data through AI chat agents

**Architecture**:


**Technologies**: Flask, Terraform, Kubernetes, AgentCore Gateway, Cognito, DynamoDB, KMS, IRSA

---

### Lambda Patterns

#### 3. MCP and Strands Implementation Using Serverless

**Repository**: [sample-serverless-mcp-servers](https://github.com/aws-samples/sample-serverless-mcp-servers)

**Pattern Type**: Pattern 1 (Lambda Event-Driven), Pattern 2 (ECS Long-Running), Pattern 9 (MCP)

**Overview**: 
A collection of sample implementations demonstrating how to build AI agents and MCP servers on AWS serverless compute (Lambda and ECS). These examples show both stateless and stateful MCP server patterns with various runtime and IaC options.

**Sample Implementations**:

| Implementation | Runtime | IaC | Pattern | Description |
|---------------|---------|-----|---------|-------------|
| **strands-agent-on-lambda** | Python (Agent), Node.js (MCP) | Terraform, CDK | Pattern 1 + 9 | AI Agent using Strands SDK with connected MCP Server on Lambda, includes Cognito authentication |
| **strands-agent-on-lambda-python** | Python | SAM | Pattern 1 | Pure Python implementation of Strands Agent on Lambda |
| **stateless-mcp-on-lambda-nodejs** | Node.js | Terraform | Pattern 1 + 9 | Remote stateless MCP Server on Lambda + API Gateway |
| **stateless-mcp-on-lambda-python** | Python | SAM | Pattern 1 + 9 | Python stateless MCP Server on Lambda + API Gateway |
| **stateless-mcp-on-ecs-nodejs** | Node.js | Terraform | Pattern 2 + 9 | Remote stateless MCP Server on ECS with ALB |
| **stateful-mcp-on-ecs-nodejs** | Node.js | Terraform | Pattern 2 + 9 | Remote stateful MCP Server on ECS with ALB and sticky sessions |
| **stateful-mcp-on-ecs-python** | Python | SAM | Pattern 2 + 9 | Python stateful MCP Server on ECS with ALB |
| **lambda-ops-mcp-server** | Node.js | Terraform | Pattern 1 + 9 | Local MCP Server for discovering and upgrading Lambda functions on deprecated runtimes |

**Key Architectural Decisions**:

**Stateful vs Stateless MCP Servers**:

*Stateful Model*:
- Maintains session state in memory
- Supports long-lived SSE (Server-Sent Events) connections
- Requires sticky sessions (cookie-based affinity) at load balancer
- Challenges: Horizontal scaling limited by session persistence
- Best for: Long-running conversations, complex multi-turn interactions
- Implementation: ECS with Application Load Balancer and manual cookie handling

*Stateless Model*:
- No session context between requests
- Seamless horizontal scaling
- Works well with Lambda's ephemeral nature
- Best for: High-volume, elastic workloads with independent requests
- Implementation: Lambda + API Gateway or ECS without session affinity

**Technical Considerations**:
- **MCP SDK Limitation**: As of early 2025, official MCP SDKs don't support external session persistence (Redis, DynamoDB)
- **TypeScript Client**: Relies on fetch API which doesn't natively support cookies, requiring manual cookie handling for stateful servers
- **Streamable HTTP Transport**: Specification allows for both stateful (with session resumption) and stateless modes

**Use Cases**:
- **Lambda Stateless**: API-driven tools, data transformations, quick queries
- **ECS Stateful**: Interactive debugging sessions, long-running analysis, conversational agents
- **Lambda Ops**: Infrastructure automation, runtime compliance, security remediation

**Benefits**:
- Multiple runtime options (Python, Node.js)
- Multiple IaC frameworks (SAM, Terraform, CDK)
- Production-ready authentication (Cognito)
- Clear trade-offs between stateful and stateless approaches
- Cost-effective serverless execution model

---

### Additional Resources

**AWS Blogs and Workshops**:
- [Automate Amazon EKS troubleshooting using Amazon Bedrock agentic workflow](https://aws.amazon.com/blogs/machine-learning/automate-amazon-eks-troubleshooting-using-an-amazon-bedrock-agentic-workflow/)
- [Agentic AI Operations Hub with Remote MCP Server on Amazon EKS](https://community.aws/content/2xKJPLLd49RjjT4eNm6KjeoGmEb/agentic-ai-operations-hub-with-remote-mcp-server-on-amazon-eks-and-amazon-bedrock)
- [Guidance for Agentic AI Operational Foundations on AWS](https://aws.amazon.com/solutions/guidance/agentic-ai-operational-foundations-on-aws/)

**Framework Documentation**:
- [Strands Agents SDK](https://github.com/awslabs/strands-agents)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- [AWS MCP Servers](https://awslabs.github.io/mcp/)

---

### Pattern Mapping to Reference Implementations

| Reference Implementation | Applicable Patterns | Key Technologies |
|-------------------------|---------------------|------------------|
| Scalable Model Inference on EKS | Pattern 4, 9, 10 | Strands SDK, Karpenter, vLLM, OpenSearch, LangFuse |
| Strands Agent on Lambda | Pattern 1, 9 | Strands SDK, Lambda, API Gateway, Cognito |
| Stateless MCP on Lambda | Pattern 1, 9 | Lambda, API Gateway, MCP SDK |
| Stateful MCP on ECS | Pattern 2, 9 | ECS, ALB, MCP SDK, Sticky Sessions |
| Lambda Ops MCP Server | Pattern 1, 7, 9 | Lambda, MCP SDK, Runtime Management |
| MCPify REST APIs with AgentCore Gateway | Pattern 8, 9 | Flask, EKS, AgentCore Gateway, Cognito, DynamoDB, KMS |

---

## License

This document is licensed under the MIT-0 License. See the LICENSE file..
