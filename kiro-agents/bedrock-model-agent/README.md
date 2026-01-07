# Bedrock Model Agent

A [Kiro CLI custom agent](https://kiro.dev/docs/cli/) that finds Amazon Bedrock model availability across AWS regions using a custom MCP server.

> **⚠️ IMPORTANT DISCLAIMER**  
> This solution uses Generative AI. Always review all code, actions, and decisions before using in production environments.

## Install Kiro CLI

1. Install Kiro CLI following the instructions [here](https://kiro.dev/docs/cli/)
2. Verify installation
   ```bash
   kiro-cli --version
   ```

## Agent Setup

1. **Clone the repository**

2. **Review agent configuration**
   - Check agent config in `.kiro/agents/bedrock-model-agent.json`
   - Check agent instructions in `.kiro/context/bedrock-model-agent/instructions.md`

3. **Ensure MCP server dependencies are installed**
   - Install Python 3.10+
   - Install `uv` from [Astral](https://docs.astral.sh/uv/getting-started/installation/)

4. **Configure AWS credentials**
   - Ensure you have AWS credentials with Bedrock permissions

## Usage

1. **Navigate to the agent directory**
   ```bash
   cd bedrock-model-agent
   ```

2. **Launch the agent**
   ```bash
   kiro-cli chat --agent bedrock-model-agent
   ```

3. **Test the agent**
   ```bash
   Is Claude 4.5 Sonnet available in us-west-2?
   ```
   ```bash
   Where is Llama 3.1 70B available?
   ```
   ```bash
   What models can I run on-demand in Dublin?
   ```

## Project Structure

```
bedrock-model-agent/
├── .kiro/
│   ├── agents/
│   │   └── bedrock-model-agent.json
│   └── context/
│       └── bedrock-model-agent/
│           └── instructions.md
├── bedrock-model-mcp/
│   ├── src/
│   │   └── bedrock_model_mcp/
│   │       ├── __init__.py
│   │       ├── models.py
│   │       └── server.py
│   ├── pyproject.toml
│   └── uv.lock
└── README.md
```

## License

MIT-0
