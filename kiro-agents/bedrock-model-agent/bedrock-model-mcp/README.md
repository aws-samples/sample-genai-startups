# Bedrock Model MCP

An MCP (Model Context Protocol) server for querying Amazon Bedrock foundation models and inference profiles across AWS regions.

## Features

- **Search Models**: Filter foundation models by provider, modality, inference type, and more
- **List Inference Profiles**: Query system-defined and application inference profiles
- **Get Providers**: List available model providers
- **Multi-Region Support**: Query single regions or all Bedrock-enabled regions in parallel using `'any'`

## Installation

```bash
uv pip install -e .
```

## Usage

### Running the Server

```bash
bedrock-model-mcp
```

### MCP Configuration

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "bedrock-model-mcp": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "<path-to-this-dir>",
        "bedrock-model-mcp"
      ]
    }
  }
}
```

## Tools

### search_models

Search and filter Bedrock foundation models.

**Parameters:**
- `regions`: AWS region(s) or `'any'` for all regions (default: `us-east-1`)
- `provider`: Filter by provider (e.g., `'Anthropic'`, `'Amazon'`, `'Meta'`)
- `inference_type`: `'ON_DEMAND'` or `'PROVISIONED'`
- `input_modality`: `'TEXT'`, `'IMAGE'`, `'VIDEO'`, `'AUDIO'`
- `output_modality`: `'TEXT'`, `'IMAGE'`, `'EMBEDDING'`
- `customization_type`: `'FINE_TUNING'`, `'CONTINUED_PRE_TRAINING'`, `'DISTILLATION'`
- `inference_profile_only`: Return only models requiring inference profiles
- `exclude_inference_profile_only`: Exclude inference-profile-only models
- `status`: `'ACTIVE'` or `'LEGACY'`
- `model_id_contains`: Filter by substring in model ID

### list_inference_profiles

List inference profiles available in a region.

**Parameters:**
- `regions`: AWS region(s) or `'any'` for all regions (default: `us-east-1`)
- `type_filter`: `'SYSTEM_DEFINED'` or `'APPLICATION'`
- `model_id_contains`: Filter by substring in profile ID

### get_model_providers

Get unique list of model providers.

**Parameters:**
- `regions`: AWS region(s) or `'any'` for all regions (default: `us-east-1`)

## Requirements

- Python >= 3.10
- AWS credentials configured with Bedrock access
- Dependencies: `boto3`, `mcp[cli]`

## Security Considerations

This MCP server runs locally and accesses AWS Bedrock APIs using your configured AWS credentials. For secure usage:

### AWS Security Best Practices (User Responsibility)
- **Use IAM roles or temporary credentials** instead of long-term access keys
- **Apply least privilege** - grant only necessary Bedrock permissions:
  - `bedrock:ListFoundationModels`
  - `bedrock:GetFoundationModel` 
  - `bedrock:ListInferenceProfiles`
- **Enable CloudTrail logging** in your AWS account for API monitoring
- **Secure local credentials** using OS credential stores and proper file permissions

### Local System Security
- Keep your system and dependencies updated
- Use secure credential storage (avoid environment variables in shared environments)
- Monitor for unusual AWS API activity in your account

For a complete security analysis, see the threat model documentation in `.threatmodel/`.

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
