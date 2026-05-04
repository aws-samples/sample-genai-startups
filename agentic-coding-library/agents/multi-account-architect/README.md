# Multi-Account Architect

The Multi-Account Architect guides startups through the transition from a single-account AWS "monolith" to a secure, multi-account Organization. It audits your live account to understand your actual resource landscape, generates tailored IaC (Terraform or CloudFormation) for your landing zone, flags cross-account dependency risks before you move anything, and tracks every migration step across sessions so you always know what's next.

## Capabilities

- **Workload Discovery Audit** — Scans your account via the Resource Groups Tagging API and classifies resources into suggested OUs (Production, Development, Unclassified) based on tags and naming conventions
- **IaC Blueprinting** — Generates Terraform or CloudFormation to bootstrap your Organization: Management, Log Archive, Security Tooling, and Workload accounts sized to your actual resource footprint
- **Dependency Pre-flight Check** — Inspects IAM roles and resource policies for hardcoded account IDs/ARNs that will break post-migration, with a remediation report for each finding
- **Persistent Migration Checklist** — Tracks migration steps (status: pending/in_progress/done/blocked) across sessions in `~/.aws-multi-account-migration-state.json`

## Installation

Copy the agent into your Kiro workspace:

```bash
cp -r agents/multi-account-architect/.kiro /path/to/your/workspace/.kiro
```

Or add it directly to an existing workspace's `.kiro/agents/` directory.

## Dependencies

### MCP Server: aws-multi-account-mcp

```bash
cd agents/multi-account-architect/aws-multi-account-mcp
uv venv && uv pip install -e .
```

### AWS Credentials

The agent uses your local AWS profile. Ensure credentials are configured:

```bash
aws sts get-caller-identity  # verify access
```

The following IAM permissions are required:
- `tag:GetResources`
- `iam:ListRoles`, `iam:ListRolePolicies`, `iam:GetRolePolicy`, `iam:ListAttachedRolePolicies`, `iam:GetPolicy`, `iam:GetPolicyVersion`
- `sts:GetCallerIdentity`

## Example Prompts

**Workload Discovery**
> "Scan my account and tell me how I should split it into OUs. My resources are tagged with the key 'Environment'."

Expected output: A categorized list of resources with suggested OU assignments and a summary of how many resources fall into Production vs Development.

**IaC Blueprinting**
> "Generate Terraform to bootstrap my new Organization structure based on what you found in the audit."

Expected output: Terraform HCL in a fenced code block defining the Organization, OUs, and account structures tailored to the audit results.

**Dependency Pre-flight Check**
> "Before I move anything, check my IAM policies for hardcoded account IDs that will break."

Expected output: A numbered remediation report listing each affected role, policy, offending ARN, and the recommended fix.

**Migration Status**
> "Where are we in the migration? What's the next step?"

Expected output: Current checklist state with completed steps and the next pending action with a concrete command or instruction.

**Author: Alena Schmickl**
