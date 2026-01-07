# Amazon Bedrock AgentCore Best Practices

## Purpose
Ensure proper deployment, configuration, and usage of Amazon Bedrock AgentCore for building production-ready AI agents with optimal performance and security.

## Instructions
- Ensure the agent invocation code uses the `@app.entrypoint` decorator
- Use `agentcore configure -e <entrypoint.py>` to configure agent deployment
- Deploy agents with `agentcore launch` for serverless runtime
- Test deployed agents using `agentcore invoke '{"prompt": "test message"}'`
- Use AgentCore Gateway to convert APIs and Lambda functions into MCP-compatible tools
- Implement proper memory infrastructure for personalized agent experiences
- Configure identity and access management for secure agent operations
- Leverage built-in Code Interpreter and Browser tools when appropriate
- Enable observability with tracing and monitoring for production deployments
- Use `.bedrock_agentcore.yaml` for deployment configuration (auto-generated)
- Structure projects with separate directories for agent-runtime, gateway, and config
- Use `pyproject.toml` for modern dependency management with AgentCore SDK

## Priority
Critical

## Error Handling
- If deployment fails, check AWS credentials and permissions
- For runtime errors, verify agent entrypoint and dependencies
- If tools fail to load, validate MCP protocol compatibility
- For memory issues, check memory infrastructure configuration
- If identity errors occur, verify IAM roles and policies
- For observability gaps, ensure OpenTelemetry configuration is correct
