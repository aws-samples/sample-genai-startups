# aws-multi-account-mcp

MCP server for auditing a single AWS account and tracking migration to a multi-account Organization.

## Prerequisites

- Python 3.10+
- AWS credentials configured locally (`~/.aws/credentials` or environment variables)
- `uv` installed

## Installation

```bash
uv venv && uv pip install -e .
```

## Tools

| Tool | Description |
|------|-------------|
| `audit_workloads` | Scans all tagged resources and classifies them into suggested OUs (Production/Development/Unclassified) based on tags and name prefixes |
| `check_dependencies` | Inspects IAM roles and policies for hardcoded account IDs/ARNs that will break post-migration |
| `get_migration_state` | Reads the persistent migration checklist from `~/.aws-multi-account-migration-state.json` |
| `update_migration_state` | Creates or updates a checklist step with a status (`pending`, `in_progress`, `done`, `blocked`) and optional notes |

## MCP Client Configuration

```json
{
  "mcpServers": {
    "aws-multi-account": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "./aws-multi-account-mcp",
        "aws-multi-account-mcp"
      ]
    }
  }
}
```
