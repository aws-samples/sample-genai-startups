# EUSC Regional Parity Analyzer

EUSC Regional Parity Analyzer is a [Kiro CLI custom agent](https://kiro.dev/docs/cli/) that compares AWS service availability between regions, identifies gaps in your specific architecture, and suggests alternatives.

> ⚠️ IMPORTANT DISCLAIMER
> This solution uses Generative AI. Always review all code, actions, and decisions before using in production environments.

This is sample code, for non-production usage. You should work with your security and legal teams to meet your organizational security, regulatory and compliance requirements before deployment.

Built for startups evaluating the [AWS European Sovereign Cloud](https://docs.aws.amazon.com/whitepapers/latest/overview-aws-european-sovereign-cloud/design-approach.html) (EUSC in this README), expanding to new AWS regions, or planning multi-region deployments. The first AWS European Sovereign Cloud Region is `eusc-de-east-1` in Brandenburg, Germany, listed by AWS as AWS European Sovereign Cloud (Germany).

The report covers service availability only. It does not assess data residency, sovereignty, or regulatory requirements, and a service being available in a region does not mean a workload there meets them. Those questions need your own legal and compliance review.

Point the agent at your infrastructure code (CDK, CloudFormation, or Terraform) or your live AWS account, specify a target region, and get a structured compatibility report showing which services are available, which are planned, and which need alternatives. The agent can:

- Extract AWS services from CDK, CloudFormation, or Terraform files (no credentials needed)
- Discover deployed services from a live AWS account via Resource Explorer (read-only)
- Check regional availability using the AWS Knowledge MCP Server
- Categorize services as available, planned, or not available in the target region
- Suggest alternatives and workarounds for unavailable services
- Generate a structured compatibility report with migration readiness scoring

## Install Kiro CLI

Follow the [Kiro CLI installation guide](https://kiro.dev/docs/getting-started/installation/) to install Kiro CLI on your platform, then verify the installation:

```bash
kiro-cli --version
```

Kiro engine: this agent is tested on the default v2 agent engine of Kiro CLI 2.27.x. Do not start it with the v3 engine (`kiro-cli --v3` or `--agent-engine v3`): with automatic agent upgrade (`chat.enableAutoAgentUpgrade`) off, the v3 engine does not load this agent and falls back to the Kiro CLI default agent, and with it on, Kiro CLI converts the agent file in place without asking and runs the converted copy. On the v3 engine, the denied paths outside the project, including hidden files and folders in your home directory, do not apply to an agent installed in a project's `.kiro/` folder, the audit log hook does not run, and in the automatically converted file the approval for file writes no longer applies. If you use the v3 engine for anything, first run `kiro-cli settings chat.enableAutoAgentUpgrade false`, do not run `/upgrade-agent` on this agent or accept an upgrade offer, and if a `.bak` file next to the agent file shows that Kiro CLI already converted it, copy this agent's `.kiro/` folder from this repository again.

## Agent Setup

1. Clone the repository and go to the agent directory:

   ```bash
   git clone https://github.com/aws-samples/sample-genai-startups.git
   cd sample-genai-startups/agentic-coding-library/agents/eusc-regional-parity-analyzer
   ```

2. Review the agent configuration:

   - `.kiro/agents/eusc-regional-parity-analyzer.json`: the system prompt, the three MCP servers and their pinned versions, the tools that run without asking, the read and write path rules, and the hooks (a startup hook that lists IaC files in your project and the audit log hook).
   - `.kiro/context/eusc-regional-parity-analyzer/guidelines.md`: how the agent detects its input, extracts services, checks availability, suggests alternatives, formats the report and the optional HTML report, and the trust and scope rules it follows.

3. Install the MCP server dependencies: Python 3.10 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/), which provides `uvx`. Kiro CLI starts these MCP servers with `uvx` on first launch, at the pinned package versions in the agent config, so there is no manual server setup:

   - `aws-iac` (`uvx awslabs.aws-iac-mcp-server@1.0.25`)
   - `aws-api` (`uvx --with mcp==1.30.0 awslabs.aws-api-mcp-server@1.5.4`)
   - `aws-knowledge` (`uvx fastmcp@4.0.3 run https://knowledge-mcp.global.api.aws`)

   | Server | Purpose | Auth required |
   |--------|---------|---------------|
   | `aws-iac` (`awslabs.aws-iac-mcp-server@1.0.25`) | Parse CDK, CloudFormation, and Terraform files, search IaC documentation | Optional; template parsing and validation run locally; the IaC documentation search tools send their queries to the public AWS Knowledge MCP Server; only the CloudFormation deployment troubleshooter (`troubleshoot_cloudformation_deployment`), which asks for your approval, uses your AWS credentials. |
   | `aws-api` (`awslabs.aws-api-mcp-server@1.5.4`) | Live resource discovery via Resource Explorer or Tag Editor API, in read-only mode | Yes (AWS credentials) |
   | `aws-knowledge`, the AWS Knowledge MCP Server (via `fastmcp@4.0.3`) | Check regional service availability, search AWS documentation for alternatives | No (public endpoint `https://knowledge-mcp.global.api.aws`, reached through `fastmcp@4.0.3`) |

   Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs. Bump the pinned versions deliberately rather than tracking `@latest`. The AWS Knowledge MCP Server is a remote endpoint that is not versioned.

   `aws-api` is launched with `--with 'mcp==1.30.0'` because the server declares `mcp>=1.23.0` with no upper bound and `mcp` 2.x renamed `McpError` to `MCPError`, so a fresh install without this pin crashes on import with `ImportError: cannot import name 'McpError'`. `mcp` 1.30.0 is the version this agent was tested with, and you can drop the `--with` once upstream publishes a correct bound.

   Upstream has announced that `awslabs.aws-api-mcp-server` is entering end of development and recommends moving to the AWS MCP Server ([migration guide](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md)). Version 1.5.4 tells the model about this in its tool descriptions, so the agent may mention the notice at the end of a session. The pinned version still works with this agent.

4. Set up credentials and permissions:

   - For IaC analysis: no additional setup is needed, just have your IaC files in the folder you start the agent from.
   - For live account scanning: AWS credentials configured with read-only access, for example a custom policy with `resource-explorer-2:Search` and `tag:GetResources` (the AWS managed `ViewOnlyAccess` policy does not include these two actions). Avoid `ReadOnlyAccess`: it also grants read access to data, such as S3 object contents and DynamoDB items, which the agent would then be able to read and send to the model provider.

## Usage

1. Kiro CLI finds workspace agents in the `.kiro/agents/` folder of the directory you launch it from, and the agent reads files from that directory, so copy the agent's `.kiro/` folder into the root of your project and launch from there. Run this from the agent directory of step 1 in Agent Setup:

   ```bash
   cp -r .kiro /path/to/your-project/
   cd /path/to/your-project
   kiro-cli chat --agent eusc-regional-parity-analyzer
   ```

   If the project already has a `.kiro/` folder, the copy adds the agent's files next to the existing ones.

2. Try one of these prompts:

   - "Analyze my CDK project for EUSC (eusc-de-east-1) compatibility": a structured report listing each service's availability in EUSC with alternatives for unavailable services.
   - "What alternatives exist for Amazon Managed Grafana in EUSC?": AWS-native alternatives (CloudWatch dashboards) and open-source options (self-hosted Grafana on ECS).
   - "Generate a migration readiness report for moving from us-east-1 to eusc-de-east-1": a full compatibility report with percentage breakdown and key migration actions.

## Security and Data Handling

- IaC mode requires no AWS credentials: the agent only reads local files.
- Live mode requires AWS credentials with read-only access. We recommend a custom policy with `resource-explorer-2:Search` and `tag:GetResources`. `ReadOnlyAccess` also grants read access to data such as S3 object contents and DynamoDB items.
- This agent interacts with your AWS account using your configured credentials. Review the permissions it requires and ensure they align with your organization's security policies.
- The agent never creates, modifies, or deletes any AWS resources.
- The `aws-api` MCP server runs with `READ_OPERATIONS_ONLY=true`: write operations are blocked at the server level.
- Keep `READ_OPERATIONS_ONLY=true` in the `aws-api` server config. If you remove it, `@aws-api/call_aws` can also run AWS CLI commands that change your account, and only the approval prompt would stand between the agent and such a change.
- Every AWS CLI command (`@aws-api/call_aws`) asks for your approval before it runs, so you see each command and can decline it. The CloudFormation deployment troubleshooter (`troubleshoot_cloudformation_deployment`) also asks for your approval. What the agent reads goes to the model provider. The approval prompt also offers to trust a tool for the rest of the session; if you accept that, later calls of that tool run without asking.
- Every file write asks for your approval first (`write` is not on the auto-approved tool list, and `requireConfirmation: true` is set). Writes to `.kiro/` and `.git/` in your project, and to hidden files and folders in your home directory (such as `~/.aws`, `~/.ssh`, and `~/.kiro`), are blocked via `toolsSettings`. Reports can be saved in your project folder.
- File reads inside the folder you start the agent from run without asking (`toolsSettings.read.allowedPaths` is `./**`); a read of any other path asks for your approval first. Reads of hidden files and folders in your home directory (such as `~/.aws` and `~/.ssh`) are denied through `toolsSettings.read.deniedPaths`, within the limits described below. What the agent reads goes to the model provider.
- These read and write path rules match file paths and are not a sandbox, so another path to the same file can get past a denied path. The config also denies the macOS path forms `/System/Volumes/Data`, `/.vol`, `/.nofollow`, and `/.resolve`, which reach the same files, but other path forms may exist. A read through such a path still asks for your approval, because it is outside the folder you started the agent from, so check what the agent wants to read before you approve. If you trust `read` for the rest of the session at an approval prompt, reads outside that folder run without asking and only the denied paths still apply.
- Do not start this agent with `--trust-all-tools`: that flag skips every approval prompt and also the denied read and write paths.
- Your IaC files are treated as untrusted input. Template comments, resource names, descriptions, tags and metadata are parsed as data, never as instructions to the agent. If a file carries text aimed at the agent, for example a comment telling it to change the target region or to mark a service available without querying, the agent ignores the text and reports it under a `Suspicious Content` heading instead.
- HTML reports: the agent's guidelines tell it to HTML-escape every value it takes from your files or tool output and to use no scripts and no external resources in the page. This is an instruction to the model, not a technical control, so review an HTML report before you share it.
- Findings never quote a credential value. If the agent spots a hardcoded secret while parsing a template it names the file and the parameter holding it, so the report stays safe to share.
- The agent will not edit its own config, prompt, or context files, and says so in its system prompt as well as being blocked from those paths.
- A `preToolUse` hook appends a timestamped audit line naming each tool call the agent attempts, including calls you then decline, to `~/.kiro/logs/eusc-regional-parity-analyzer-audit.log`. Calls refused by a denied read or write path are rejected before the hook runs and are not logged. It records tool names only, never payloads, so customer template content never lands in the log. It cannot block or fail a session if that path is unwritable.
- MCP server packages are pinned to exact versions, so a new upstream release of a server is not picked up through a silent `@latest` resolution. Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs.
- The agent does not store your AWS credentials. Its tools use them on your machine to sign read-only AWS API calls, and the agent is instructed never to repeat a credential value. What the agent reads during a session (your files, tool output, and AWS API responses, which can include account metadata such as account IDs, ARNs, and resource names) is sent to the model provider that Kiro CLI uses, so that the model can answer. Availability and documentation lookups send their query terms to the public AWS Knowledge MCP Server (`https://knowledge-mcp.global.api.aws`). Apart from the report files you approve, the agent's own configuration writes only the local audit log described above (`~/.kiro/logs/eusc-regional-parity-analyzer-audit.log`, timestamps and tool names only). The MCP servers and `uvx` may keep their own local caches and logs. Kiro CLI itself can keep the conversation locally so you can resume it (`kiro-cli chat --resume`).
- Recommendations and outputs are generated by an AI model and may contain inaccuracies. Always verify suggestions before acting on them, especially for cost, security, or infrastructure changes.
- Use of this agent is subject to the [AWS Customer Agreement](https://aws.amazon.com/agreement/) and the [AWS Acceptable Use Policy](https://aws.amazon.com/aup/).
- The authors and AWS are not responsible for any costs, damages, or security issues arising from the use of this agent.

## Project Structure

```
eusc-regional-parity-analyzer/
├── .kiro/
│   ├── agents/
│   │   └── eusc-regional-parity-analyzer.json
│   └── context/
│       └── eusc-regional-parity-analyzer/
│           └── guidelines.md
└── README.md
```

## License

This sample is licensed under the MIT-0 License, see the [LICENSE](https://github.com/aws-samples/sample-genai-startups/blob/main/LICENSE) file.

## Contributors

- Alexander Barge
