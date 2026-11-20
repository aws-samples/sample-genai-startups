# Cost Translator

Cost Translator is a [Kiro CLI custom agent](https://kiro.dev/docs/cli/) that translates AWS costs into business metrics (cost per user, cost by business function, scaling projections at 2.5x, 10x, and 25x your current user base, break-even points, investor-ready summaries with unit economics, and savings opportunities such as Reserved Instances, Savings Plans, and rightsizing) for startup founders and finance leads who think in users, features, and margins rather than service names.

> ⚠️ IMPORTANT DISCLAIMER
> This solution uses Generative AI. Always review all code, actions, and decisions before using in production environments.

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
   cd sample-genai-startups/agentic-coding-library/agents/cost-translator
   ```

2. Review the agent configuration:

   - `.kiro/agents/cost-translator.json`: the agent definition, with the prompt, the four MCP servers and their pinned versions, the tool list and which tools run without asking, the read and write path rules, and the start-up and audit log hooks.
   - `.kiro/context/cost-translator/guidelines.md`: the security boundaries, input mode detection, when to use each tool, the service-to-function mapping, scaling and break-even rules, and the output formats.

3. Install the MCP server dependencies: Python 3.10 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/), which provides `uvx`. Kiro CLI starts these MCP servers with `uvx` on first launch, at the pinned package versions in the agent config:

   - `billing` (`uvx awslabs.billing-cost-management-mcp-server@0.0.36`)
   - `pricing` (`uvx awslabs.aws-pricing-mcp-server@1.1.0`)
   - `aws-api` (`uvx --with mcp==1.30.0 awslabs.aws-api-mcp-server@1.5.4`)
   - `docs` (`uvx awslabs.aws-documentation-mcp-server@1.2.0`)

   Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs.

   The `--with 'mcp==1.30.0'` pin on `aws-api` works around an upstream packaging bug: the server declares `mcp>=1.23.0` with no upper bound, and `mcp` 2.x renamed `McpError` to `MCPError`, so a fresh install without the pin crashes on import. `mcp` 1.30.0 is the version this agent was tested with.

   Upstream has announced that `awslabs.aws-api-mcp-server` is entering end of development and recommends moving to the AWS MCP Server ([migration guide](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md)). Version 1.5.4 tells the model about this in its tool descriptions, so the agent may mention the notice at the end of a session. The pinned version still works with this agent.

4. Set up AWS credentials for the input mode you want to use. The agent supports three ways to provide cost data:

   | Mode | Input | AWS Credentials | Best For |
   |------|-------|-----------------|----------|
   | IaC Estimation | CloudFormation, Terraform, or CDK files in workspace | Needed for price lookups (`pricing:*` read actions); finding the services in your files needs none | Pre-deployment cost planning |
   | Live Cost Data | Actual AWS billing data | Read-only (see the Minimal IAM Policy below) | Existing accounts with real spend |
   | Manual Input | You provide the numbers (e.g., "EC2 $450, RDS $280") | Not needed | Quick analysis, budget planning |

   - For live cost data mode: AWS credentials with read-only access (see the Minimal IAM Policy below).
   - For IaC estimation: AWS credentials that can call the AWS Price List API (the `pricing:*` actions in the policy below), because price lookups are AWS API calls.

   Minimal IAM Policy (Live Cost Data Mode):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ce:GetCostAndUsage",
           "ce:GetCostForecast",
           "ce:GetDimensionValues",
           "ce:GetTags",
           "ce:GetCostAndUsageComparisons",
           "ce:GetCostComparisonDrivers",
           "ce:GetSavingsPlansCoverage",
           "ce:GetSavingsPlansUtilization",
           "ce:GetReservationCoverage",
           "ce:GetReservationUtilization",
           "ce:GetAnomalies",
           "cost-optimization-hub:ListRecommendations",
           "cost-optimization-hub:ListRecommendationSummaries",
           "cost-optimization-hub:GetRecommendation",
           "budgets:ViewBudget",
           "pricing:DescribeServices",
           "pricing:GetAttributeValues",
           "pricing:GetProducts",
           "pricing:GetPriceListFileUrl"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

   This policy grants read-only access to the Cost Explorer, Cost Optimization Hub, Budgets, and Pricing APIs: the Savings Plans and Reserved Instance coverage and utilization reads, the anomaly and budget reads, and the Cost Optimization Hub reads the agent uses for savings recommendations (Cost Optimization Hub must be enabled for the account). The `aws-api` resource descriptions need extra read-only actions for the services you want described; add only the ones you need. The billing `cost-explorer` tool can also call `ce:GetCostAndUsageWithResources`, `ce:GetCostCategories`, and `ce:GetUsageForecast`; this policy leaves them out, so such calls fail with AccessDenied. Add them only if you want those views. None of the agent's billing tools changes billing settings, budgets, or resources.

## Usage

1. Copy the agent into your project and start it there. Kiro CLI finds workspace agents in the `.kiro/agents/` folder of the directory you launch it from, and the agent reads files (such as your IaC files) from that directory. Run this from the agent directory of Agent Setup step 1:

   ```bash
   cp -r .kiro /path/to/your-project/
   cd /path/to/your-project
   kiro-cli chat --agent cost-translator
   ```

   If the project already has a `.kiro/` folder, the copy adds the agent's files next to the existing ones.

2. Try one of these prompts:

   - "What's my AWS cost per user? We have 4,000 monthly active users." Expected output: total monthly cost, cost per user, and a breakdown by business function with per-user costs.
   - "How much will our AWS bill be at 50,000 users?" Expected output: projected monthly cost at 50K users, cost per user at that scale, and the services that need architectural changes.
   - "What's our infrastructure break-even point at $10/user/month pricing?" Expected output: break-even user count, fixed vs variable cost split, and margin at different scales.

## Cost Considerations

The AWS Cost Explorer API charges $0.01 per API request. Each query the agent makes to fetch billing data (e.g., `GetCostAndUsage`, `GetCostForecast`) incurs this charge. A typical session makes 2 to 5 API calls, and each one asks for your approval first. The AWS Pricing API is free of charge.

For current pricing, see the [AWS Cost Explorer Pricing page](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/).

## Security and Data Handling

This agent reads real billing and cost data, so the limits around it matter. The full set lives in the Security Boundaries section of `.kiro/context/cost-translator/guidelines.md`; the enforcement lives in the agent config.

### MCP Servers

| Server | Pinned version | Startup timeout | Purpose |
|--------|----------------|-----------------|---------|
| `awslabs.billing-cost-management-mcp-server` | `0.0.36` | 30s | Actual billing data, cost forecasts, Savings Plans and RI coverage, savings recommendations. The agent loads only eight of this server's tools: `cost-explorer`, `cost-comparison`, `sp-performance`, `ri-performance`, `cost-optimization`, `cost-anomaly`, `budgets`, and `session-sql` (a query on a temporary local table the server keeps for large results) |
| `awslabs.aws-pricing-mcp-server` | `1.1.0` | 60s | Service pricing lookups and IaC cost estimation. The agent loads eight of this server's nine tools; `generate_cost_report` is not loaded, because it writes files from the server process, outside the write rules below |
| `awslabs.aws-api-mcp-server` | `1.5.4` | 30s | Resource configuration descriptions (read-only) |
| `awslabs.aws-documentation-mcp-server` | `1.2.0` | 30s | AWS docs for pricing models and scaling characteristics |

The pricing server gets the longer timeout because it parses whole CDK and Terraform projects on a cold start.

### Security Controls

| Control | How it is enforced |
|---------|--------------------|
| Read-only against AWS | `@aws-api` runs with `READ_OPERATIONS_ONLY=true`. This matters because `call_aws` is a generic AWS CLI passthrough. Keep `READ_OPERATIONS_ONLY=true` in the `aws-api` server config. If you remove it, `@aws-api/call_aws` can also run AWS CLI commands that change your account, and only the approval prompt would stand between the agent and such a change. From the billing server the agent loads only the eight read tools listed under MCP Servers; the server's other tools, some of which create Athena tables or start Cost Explorer analyses, are not loaded. The prompt states the read-only and advisory posture |
| Approval for AWS calls | Only file reads inside your project folder, pricing lookups, IaC analysis, AWS command suggestions, and documentation tools run without asking. Every AWS CLI command (`@aws-api/call_aws`) and every billing and Cost Explorer call (the eight `@billing` tools) ask for your approval before they run, so you see each call and can decline it. Each Cost Explorer request costs $0.01. The approval prompt also offers to trust a tool for the rest of the session; if you accept that, later calls of that tool run without asking |
| No exfiltration of account cost data | Prompt and guidelines forbid sending, sharing, or forwarding cost data, account identifiers, or resource inventories anywhere outside the session. The agent also has no `web`, `fetch`, or `shell` tool, so it has no general-purpose outbound path to misuse |
| Untrusted input handling | Prompt and guidelines treat user input, file content, IaC comments, billing tags, resource names, and tool output as untrusted data, and require reporting embedded instructions as a suspected injection attempt rather than acting on them |
| HTML report safety | The guidelines tell the agent to HTML-escape every value it takes from your files or tool output and to use no scripts and no external resources in the page. This is an instruction to the model, not a technical control, so review an HTML report before you share it |
| No self-modification | `toolsSettings.write.deniedPaths` blocks `.kiro/**` and `.git/**` in your project and hidden files and folders in your home directory (`~/.*`, `~/.*/**`, which covers `~/.aws`, `~/.ssh`, and `~/.kiro`); the prompt forbids changing the agent's own configuration, prompt, or context files. The pricing server's `generate_cost_report` tool, which writes files from the server process where these path rules do not apply, is not loaded, so every file the agent saves goes through `write` and these path rules. Reports can be saved in your project folder |
| No reads of home secrets | File reads inside the folder you start the agent from run without asking (`toolsSettings.read.allowedPaths` is `./**`); a read of any other path asks for your approval first. `toolsSettings.read.deniedPaths` denies reads of hidden files and folders in your home directory (`~/.*`, `~/.*/**`, such as `~/.aws` and `~/.ssh`), within the limits described below. What the agent reads goes to the model provider. These read and write path rules match file paths and are not a sandbox, so another path to the same file can get past a denied path. The config also denies the macOS path forms `/System/Volumes/Data`, `/.vol`, `/.nofollow`, and `/.resolve`, which reach the same files, but other path forms may exist. A read through such a path still asks for your approval, because it is outside the folder you started the agent from, so check what the agent wants to read before you approve. If you trust `read` for the rest of the session at an approval prompt, reads outside that folder run without asking and only the denied paths still apply |
| Human in the loop on writes | `write` is not on the auto-approved tool list and `toolsSettings.write.requireConfirmation` is `true`, so every file write asks for your approval before it happens |
| No blanket trust | Do not start this agent with `--trust-all-tools`: that flag skips every approval prompt and also the denied read and write paths. Start the agent with plain `kiro-cli chat --agent cost-translator` |
| Pinned server versions | All four server packages are pinned to exact versions. Change a pin deliberately, not by drifting to whatever `uvx` resolves that day. Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs |
| Audit trail | A `preToolUse` hook appends one timestamped line per tool call the agent attempts, including calls you then decline, to `~/.kiro/logs/cost-translator-audit.log`, outside the repository. Calls refused by a denied read or write path are rejected before the hook runs and are not logged. It records the tool name only, never arguments or account data, and it exits cleanly and silently if it cannot write |
| Scoped context | `resources` points at `.kiro/context/cost-translator/*.md` rather than a recursive glob |
| Model | `null`, a deliberate choice to defer to the model the Kiro CLI manages rather than hard-code an ID that ages out. Verified against the CLI: a pinned ID stops resolving once that model is retired, which is a live failure for anyone who installs this agent later |

### Caller identity at start-up

When the agent starts, its `agentSpawn` hook runs `aws sts get-caller-identity` to see whether AWS credentials are configured. The output (your AWS account ID; the IAM ARN, which names the user or role and, for an assumed role, the session name; and the UserId) goes into the model context and is sent to the model provider for the rest of the session, in every mode, including IaC estimation and manual input. The agent is instructed not to put account identifiers in its reports. If you do not want them in the session, launch the agent from a shell where no AWS credentials are configured; manual input still works, and IaC estimation can still find the services in your files but cannot look up prices.

### Disclaimer and data handling

This agent is provided as a sample for educational and demonstration purposes only. It is not intended for production use without thorough review and testing in your own environment.

- This agent interacts with your AWS account using your configured credentials. Review the permissions it requires and ensure they align with your organization's security policies.
- Recommendations and outputs are generated by an AI model and may contain inaccuracies. Always verify suggestions before acting on them, especially for cost, security, or infrastructure changes.
- The agent does not store your AWS credentials. Its tools use them on your machine to sign read-only AWS API calls, and the agent is instructed never to repeat a credential value. What the agent reads during a session (your files, tool output, and AWS API responses, which can include account metadata such as account IDs, ARNs, and resource names) is sent to the model provider that Kiro CLI uses, so that the model can answer. This includes the caller identity (account ID, IAM ARN, and UserId) that the start-up hook adds to every session, described under Caller identity at start-up above. Documentation lookups send their search terms to public AWS documentation endpoints. Apart from the report files you approve, the agent's own configuration writes only the local audit log described above (`~/.kiro/logs/cost-translator-audit.log`, timestamps and tool names only). The MCP servers and `uvx` may keep their own local caches and logs. Kiro CLI itself can keep the conversation locally so you can resume it (`kiro-cli chat --resume`).
- Use of this agent is subject to the [AWS Customer Agreement](https://aws.amazon.com/agreement/) and the [AWS Acceptable Use Policy](https://aws.amazon.com/aup/).
- The authors and AWS are not responsible for any costs, damages, or security issues arising from the use of this agent.

## Project Structure

```
cost-translator/
├── .kiro/
│   ├── agents/
│   │   └── cost-translator.json
│   └── context/
│       └── cost-translator/
│           └── guidelines.md
└── README.md
```

## License

This sample is licensed under the [MIT-0 License](https://github.com/aws-samples/sample-genai-startups/blob/main/LICENSE).

## Contributors

- Alexander Barge
