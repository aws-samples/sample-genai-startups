# Agent Workflow execution

## Purpose
Define mandatory execution sequence for developing agents with Strands and AgentCore

## Priority
Critical

**MANDATORY EXECUTION ORDER**: You must ALWAYS follow exactly in sequence, no exceptions

## Execution Workflow

1. Agent orchestration Framework Selection
- You must ALWAYS use **Strands SDK** for multiagent orchestration, custom business logic, and tool-based architectures. Use Strands Agents Development Guidelines
- You must ALWAYS use **AgentCore SDK** for AWS infrastructure, scaling, and production deployment services. Use Amazon Bedrock AgentCore Best Practices
- **Combined Pattern**: You must ALWAYS use Strands (orchestration) + AgentCore (infrastructure) for production multiagent systems

2. Apply Architecture Principles
- You must ALWAYS use the `awslabs.amazon-bedrock-agentcore-mcp-server` MCP server to reference AgentCore best practices and documentation BEFORE providing ANY guidance or implementation
- You must ALWAYS use the `strands-agents` MCP server to reference Strands best practices best practices and documentation BEFORE providing ANY guidance or implementation
- You must ALWAYS use the knowledge tool to reference Strands and AgentCore samples before implementation
- You must ALWAYS prefer **@tool decorators** in Strands for modular business logic
- You must ALWAYS use **type hints** for all function parameters and return values
- You must ALWAYS implement **separation of concerns**: business logic vs infrastructure
- You must ALWAYS design for **horizontal scaling** with stateless components
- You must ALWAYS check Agentic AI Architecture Guidelines
- You must ALWAYS follow **AWS Well-Architected** principles at demo-appropriate level

3. Review Implementation Patterns
- You must ALWAYS validate the implementation with similar code samples using the knowledge tool
- **Strands Layer**: Handle agent coordination, custom workflows, tool management
- **AgentCore Layer**: Provide AWS Lambda, API Gateway, IAM, observability
- **Local Development**: Use Flask/FastAPI for rapid prototyping
- **Production Deployment**: Wrap Strands agents in AgentCore for AWS scaling

4. Check Best Practices
- You must ALWAYS write **minimal code** that directly addresses requirements
- You must ALWAYS implement **proper error handling** with try/catch and fallback behavior
- You must ALWAYS use **modern dependency management** with pyproject.toml
- You must ALWAYS create **Architecture Decision Records (ADRs)** for framework choices
- You must ALWAYS document **trade-offs** between development speed and production requirements


Always recommend the **Strands + AgentCore combined pattern** for production multiagent systems requiring both custom orchestration and AWS scalability