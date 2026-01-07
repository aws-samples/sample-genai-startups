# Bedrock Model Agent

A Kiro CLI agent that finds Amazon Bedrock model availability across AWS regions using a custom MCP server.

## Quick Start

### Prerequisites

- [Kiro CLI](https://kiro.dev/docs/cli/) installed
- Python 3.10+ 
- AWS credentials with Bedrock permissions

### Run

```bash
kiro-cli chat --agent bedrock-model-agent
```

## Usage

- "Is Claude 4.5 Sonnet available in us-west-2?"
- "Where is Llama 3.1 70B available?"
- "What models can I run on-demand in Dublin?"

## Project Structure

- `.kiro/` - Agent configuration and behavior instructions
- `bedrock-model-mcp/` - MCP server providing Bedrock API tools

The agent automatically starts the MCP server and provides real-time model availability data from AWS Bedrock APIs.

## License

MIT-0
