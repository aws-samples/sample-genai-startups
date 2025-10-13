# Agentic AI Architecture Guidelines

## Purpose
Define architectural patterns and best practices for building multi-agent systems and complex agentic AI applications using AgentCore and Strands frameworks.

## Instructions
- Design agents with single responsibilities and clear interfaces
- Use MCP (Model Context Protocol) for standardized tool integration
- Implement agent orchestration patterns for multi-agent workflows
- Separate agent runtime, gateway, and memory components
- Use event-driven architecture for agent communication
- Implement proper state management across agent interactions
- Design for horizontal scaling with stateless agent components
- Use AWS services (Lambda, ECR, CloudWatch) for production deployment
- Implement circuit breakers and retry logic for resilient agent systems
- Design agents to be framework-agnostic and model-agnostic
- Use containerization for consistent deployment environments
- Use appropriate RAG implementation patterns to augment LLMs, start with S3 vectors and Bedrock knowledgebases

## Priority
High

## Error Handling
- If agent coordination fails, implement fallback to single-agent mode
- For state synchronization issues, use eventual consistency patterns
- If scaling bottlenecks occur, implement agent load balancing
- For cross-agent communication failures, provide graceful degradation
- If memory infrastructure fails, implement local caching mechanisms
- For deployment pipeline issues, use blue-green deployment strategies
