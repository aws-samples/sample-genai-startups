# Explain My AWS

Explain My AWS is a [Kiro CLI custom agent](https://kiro.dev/docs/cli/) that translates AWS infrastructure into plain English for non-technical startup stakeholders. Point it at your CDK, CloudFormation, or Terraform code or connect it to your AWS account, and it generates a complete infrastructure report: plain-English summary, architecture diagram, cost breakdown, risk flags, and an investor-ready one-pager.

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
   cd sample-genai-startups/agentic-coding-library/agents/explain-my-aws
   ```

2. Review the agent configuration:

   - `.kiro/agents/explain-my-aws.json`: the agent prompt, the MCP servers and their pinned versions, the tool list and which tools run without asking, the read and write path rules, and the start-up and audit log hooks.
   - `.kiro/context/explain-my-aws/guidelines.md`: how the agent picks a mode, the report sections and their format, tool usage, security constraints, and the rules for HTML reports.

3. Install the MCP server dependencies: Python 3.10 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/), which provides `uvx`. Kiro CLI starts these MCP servers with `uvx` on first launch, at the pinned package versions in the agent config:

   - `iac` (`uvx awslabs.aws-iac-mcp-server@1.0.25`): CDK and CloudFormation documentation search for understanding resource types.
   - `pricing` (`uvx awslabs.aws-pricing-mcp-server@1.1.0`): CDK and Terraform project analysis and real-time pricing queries. The agent loads eight of this server's nine tools; `generate_cost_report` is not loaded, because it writes files from the server process, outside the write rules below.
   - `billing` (`uvx awslabs.billing-cost-management-mcp-server@0.0.36`): actual AWS spend by service and cost forecasts (through the Cost Explorer API). The agent loads only two of this server's tools: `cost-explorer` and `session-sql`, which queries a temporary local table the server keeps for large results.
   - `aws-api` (`uvx --with mcp==1.30.0 awslabs.aws-api-mcp-server@1.5.4`): read-only AWS CLI commands to describe live resources.
   - `docs` (`uvx awslabs.aws-documentation-mcp-server@1.2.0`): plain-English AWS service descriptions and best practices.

   Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs. To take a newer upstream release, bump the version in `.kiro/agents/explain-my-aws.json`.

   The `--with 'mcp==1.30.0'` pin for `aws-api` works around an upstream packaging bug: the server declares `mcp>=1.23.0` with no upper bound, and `mcp` 2.x renamed `McpError` to `MCPError`, so a fresh install without the pin crashes on import. `mcp` 1.30.0 is the version this agent was tested with.

   Upstream has announced that `awslabs.aws-api-mcp-server` is entering end of development and recommends moving to the AWS MCP Server ([migration guide](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md)). Version 1.5.4 tells the model about this in its tool descriptions, so the agent may mention the notice at the end of a session. The pinned version still works with this agent.

4. Set up AWS credentials and permissions for the mode you want. The agent auto-detects which mode to use based on your environment.

   - Mode 1 (IaC Analysis): scans CDK, CloudFormation, or Terraform files in your project. Best for teams with infrastructure as code. Reading and explaining the files needs no AWS credentials. The cost section looks up prices in the AWS Price List API, which needs AWS credentials (an identity allowed `pricing:GetProducts` and `pricing:DescribeServices` is enough). Without credentials, the agent still explains your infrastructure but leaves prices out.
   - Mode 2 (Live Account Discovery): queries your AWS account directly using Cost Explorer and read-only API calls. Best for startups that built through the AWS console without infrastructure as code. Requires AWS credentials configured with read-only access.

   For Mode 2, create a read-only IAM role with this minimum policy:

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
           "ec2:Describe*",
           "rds:Describe*",
           "s3:ListBuckets",
           "s3:GetBucketLocation",
           "ecs:Describe*",
           "ecs:List*",
           "lambda:ListFunctions",
           "elasticloadbalancing:Describe*",
           "cloudfront:List*",
           "cloudwatch:GetMetricData",
           "pricing:GetProducts",
           "pricing:DescribeServices"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

   The `Describe*` and `List*` wildcards keep this example short. For production use, replace them with the specific actions your account needs. Note that `lambda:ListFunctions` returns each function's environment variables, which often hold secrets, and the agent sends what it reads to the model provider.

   Prefer this policy over the AWS managed `ReadOnlyAccess` policy. `ReadOnlyAccess` also grants read access to data, such as S3 object contents and DynamoDB items, which the agent would then be able to read and send to the model provider.

   The billing `cost-explorer` tool can also call `ce:GetCostAndUsageWithResources`, `ce:GetCostCategories`, `ce:GetUsageForecast`, and `ce:GetSavingsPlansUtilization`. This policy leaves them out, so such calls fail with AccessDenied; add them only if you want those views.

   To change the default AWS region for pricing lookups, edit the `AWS_REGION` env var in `.kiro/agents/explain-my-aws.json`.

## Usage

1. Copy the agent into the project you want explained and launch it. Kiro CLI finds workspace agents in the `.kiro/agents/` folder of the directory you launch it from, and the agent reads files from that directory. From the agent directory of Agent Setup step 1, run:

   ```bash
   cp -r .kiro /path/to/your-project/
   cd /path/to/your-project
   kiro-cli chat --agent explain-my-aws
   ```

   If the project already has a `.kiro/` folder, the copy adds the agent's files next to the existing ones.

2. Try an example prompt:

   - "Explain our AWS infrastructure in plain English": the agent scans your project for CDK, CloudFormation, or Terraform files and generates all 5 report sections.
   - "How much does our AWS setup cost per month? Break it down by component.": a table of monthly costs by service with percentage of total and a per-user calculation.
   - "Connect to my AWS account and explain what we're running": uses Cost Explorer and the AWS API to discover and explain your live infrastructure.

## Cost Warning

Mode 2 (Live Account Discovery) uses the AWS Cost Explorer API, which charges $0.01 per API request. A typical infrastructure report may make 3 to 10 Cost Explorer API calls, and each one asks for your approval first. This is usually under $0.10 per report, but be aware of the cost if running the agent frequently. Mode 1 (IaC Analysis) uses the AWS Pricing API, which is free of charge.

## Security and Data Handling

- Mode 1 (IaC): Reading and explaining IaC needs no AWS credentials, and the agent only reads local files. Price lookups need AWS credentials (see Agent Setup step 4). If credentials are present, the start-up hook still runs `aws sts get-caller-identity` (see Caller identity at start-up below).
- Mode 2 (Live): Requires AWS credentials. AWS access is read-only: the `aws-api` MCP server runs with `READ_OPERATIONS_ONLY=true`, and from the billing server the agent loads only `cost-explorer` (Cost Explorer read calls) and `session-sql` (a local query that does not call AWS). The billing server's other tools, some of which create Athena tables or start Cost Explorer analyses, are not loaded.
- Approval for AWS calls: every AWS CLI command (`@aws-api/call_aws`) and every billing call (`@billing/cost-explorer` and `@billing/session-sql`) asks for your approval before it runs, so you see each command and can decline it. Read calls can still return sensitive data, such as Lambda environment variables, and what the agent reads goes to the model provider. The approval prompt also offers to trust a tool for the rest of the session; if you accept that, later calls of that tool run without asking.
- With these settings, none of the agent's tools can create, modify, or delete AWS resources. Keep `READ_OPERATIONS_ONLY=true` in the `aws-api` server config. If you remove it, `@aws-api/call_aws` can also run AWS CLI commands that change your account, and only the approval prompt would stand between the agent and such a change.
- Write paths are restricted: the agent cannot write to `.kiro/` or `.git/` in your project, or to hidden files and folders in your home directory (such as `~/.aws`, `~/.ssh`, and `~/.kiro`). Reports can be saved in your project folder.
- File reads inside the folder you start the agent from run without asking (`toolsSettings.read.allowedPaths` is `./**`); a read of any other path asks for your approval first. Reads of hidden files and folders in your home directory (such as `~/.aws` and `~/.ssh`) are denied through `toolsSettings.read.deniedPaths`, within the limits described below. What the agent reads goes to the model provider.
- These read and write path rules match file paths and are not a sandbox, so another path to the same file can get past a denied path. The config also denies the macOS path forms `/System/Volumes/Data`, `/.vol`, `/.nofollow`, and `/.resolve`, which reach the same files, but other path forms may exist. A read through such a path still asks for your approval, because it is outside the folder you started the agent from, so check what the agent wants to read before you approve. If you trust `read` for the rest of the session at an approval prompt, reads outside that folder run without asking and only the denied paths still apply.
- Do not start this agent with `--trust-all-tools`: that flag skips every approval prompt and also the denied read and write paths.
- File writes ask for your approval each time (`write` is not on the agent's auto-approved tool list, and `toolsSettings.write.requireConfirmation` is set), so the agent cannot save a report without an explicit go-ahead.
- Untrusted input: the agent treats IaC file content, resource names, tags, and AWS API responses as untrusted data rather than as instructions. If a template or tag contains text aimed at steering the output, the agent reports it as a HIGH risk flag named "possible prompt injection" instead of acting on it. This matters because the report is written for readers who cannot sanity-check it.
- HTML reports: the agent's guidelines tell it to HTML-escape every value it takes from your files or tool output and to use no scripts and no external resources in the page. This is an instruction to the model, not a technical control, so review an HTML report before you share it.
- No exfiltration: the agent never sends account inventory, cost figures, or file content to any external or third-party destination. Apart from the model provider that runs the session (see Data handling below), its only outbound calls are the read-only AWS and AWS documentation lookups made by its MCP tools.
- The agent cannot change its own configuration, prompt, or context files at runtime. The pricing server's `generate_cost_report` tool, which writes files from the server process where the write path rules do not apply, is not loaded, so every file the agent saves goes through `write` and these path rules.
- Audit trail: a `preToolUse` hook appends a timestamped line naming each tool call the agent attempts, including calls you then decline, to `~/.kiro/logs/explain-my-aws-audit.log`, or to `$KIRO_AUDIT_LOG` if you set it. Calls refused by a denied read or write path are rejected before the hook runs and are not logged. It records the tool name only, not arguments, so account data never lands in the log. The hook always exits successfully, so a missing or unwritable log path never blocks the agent.
- MCP server packages are pinned to exact versions in the agent config, so a new upstream release of a server cannot silently change behaviour. Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs.

### Caller identity at start-up

When the agent starts, its `agentSpawn` hook runs `aws sts get-caller-identity` to see whether AWS credentials are configured. The output (your AWS account ID; the IAM ARN, which names the user or role and, for an assumed role, the session name; and the UserId) goes into the model context and is sent to the model provider for the rest of the session, in every mode, including IaC analysis. The agent is instructed not to repeat these values in its reports. If you do not want them in the session, launch the agent from a shell where no AWS credentials are configured; IaC analysis still works, but without price lookups.

### Data handling

This agent is provided as a sample for educational and demonstration purposes only. It is not intended for production use without thorough review and testing in your own environment.

- This agent interacts with your AWS account using your configured credentials. Review the permissions it requires and ensure they align with your organization's security policies.
- Recommendations and outputs are generated by an AI model and may contain inaccuracies. Always verify suggestions before acting on them, especially for cost, security, or infrastructure changes.
- The agent does not store your AWS credentials. Its tools use them on your machine to sign read-only AWS API calls, and the agent is instructed never to repeat a credential value. What the agent reads during a session (your files, tool output, and AWS API responses, which can include account metadata such as account IDs, ARNs, and resource names) is sent to the model provider that Kiro CLI uses, so that the model can answer. This includes the caller identity (account ID, IAM ARN, and UserId) that the start-up hook adds to every session, described under Caller identity at start-up above. Documentation lookups send their search terms to public AWS documentation endpoints. Apart from the report files you approve, the agent's own configuration writes only the local audit log described above (`~/.kiro/logs/explain-my-aws-audit.log`, or `$KIRO_AUDIT_LOG` if you set it, timestamps and tool names only). The MCP servers and `uvx` may keep their own local caches and logs. Kiro CLI itself can keep the conversation locally so you can resume it (`kiro-cli chat --resume`).
- Use of this agent is subject to the [AWS Customer Agreement](https://aws.amazon.com/agreement/) and the [AWS Acceptable Use Policy](https://aws.amazon.com/aup/).
- The authors and AWS are not responsible for any costs, damages, or security issues arising from the use of this agent.

## Project Structure

```
explain-my-aws/
├── .kiro/
│   ├── agents/
│   │   └── explain-my-aws.json
│   └── context/
│       └── explain-my-aws/
│           └── guidelines.md
└── README.md
```

## License

This sample is licensed under the MIT-0 License. See the [LICENSE](https://github.com/aws-samples/sample-genai-startups/blob/main/LICENSE) file.

## Contributors

- Alexander Barge
