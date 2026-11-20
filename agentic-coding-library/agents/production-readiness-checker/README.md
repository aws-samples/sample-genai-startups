# Production Readiness Checker

Production Readiness Checker is a [Kiro CLI custom agent](https://kiro.dev/docs/cli/) that reviews your startup's codebase and infrastructure-as-code against a 5-pillar production readiness checklist (security, cost, resilience, observability, and governance controls) and generates a prioritized action plan with severity-ranked findings and code fixes.

> ⚠️ IMPORTANT DISCLAIMER
> This solution uses Generative AI. Always review all code, actions, and decisions before using in production environments.

This is sample code, for non-production usage. You should work with your security and legal teams to meet your organizational security, regulatory and compliance requirements before deployment.

It is an advisory review of technical controls: it reports what it observes in your code and account. It does not assess, score, or certify compliance with SOC 2, GDPR, HIPAA, or any other framework, and following its fixes does not make you compliant with one. If you need that answer, take the governance controls it lists to your auditor or compliance advisor.

It is built for seed-stage CTOs asking "Am I ready for production?", and it combines the AWS Startup Security Baseline (SSB), Startup Resiliency Baseline (SRB), and Well-Architected Framework into a single, startup-opinionated check. It can:

- Analyze CDK, CloudFormation, and Terraform IaC against a 30-item checklist
- Check live security service status (GuardDuty, Security Hub, Inspector), security findings, network security, and storage encryption via the Well-Architected Security MCP server
- Verify CloudWatch monitoring and alerting configuration
- Check live resource configurations (MFA, backups, encryption, public access)
- Reference SSB, SRB, and Well-Architected best practices from official docs
- Generate a scored report with critical/important/good findings and code fixes

## Install Kiro CLI

Follow the [Kiro CLI installation guide](https://kiro.dev/docs/getting-started/installation/) to install Kiro CLI on your platform, then verify the installation:

```bash
kiro-cli --version
```

Kiro engine: this agent is tested on the default v2 agent engine of Kiro CLI 2.27.x. Do not start it with the v3 engine (`kiro-cli --v3` or `--agent-engine v3`): with automatic agent upgrade (`chat.enableAutoAgentUpgrade`) off, the v3 engine does not load this agent and falls back to the Kiro CLI default agent, and with it on, Kiro CLI converts the agent file in place without asking and runs the converted copy. On the v3 engine, the denied paths outside the project, including hidden files and folders in your home directory, do not apply to an agent installed in a project's `.kiro/` folder, the audit log hook does not run, and in the automatically converted file the approval for file writes no longer applies. If you use the v3 engine for anything, first run `kiro-cli settings chat.enableAutoAgentUpgrade false`, do not run `/upgrade-agent` on this agent or accept an upgrade offer, and if a `.bak` file next to the agent file shows that Kiro CLI already converted it, copy this agent's `.kiro/` folder from this repository again.

## Agent Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/aws-samples/sample-genai-startups.git
   cd sample-genai-startups/agentic-coding-library/agents/production-readiness-checker
   ```

2. Review the agent configuration:

   - `.kiro/agents/production-readiness-checker.json`: the agent definition, with its prompt, MCP servers, auto-approved tools, read and write path rules, and hooks.
   - `.kiro/context/production-readiness-checker/checklist.md`: the 30-item checklist across the 5 pillars, with a severity and check mode for each item.
   - `.kiro/context/production-readiness-checker/guidelines.md`: the operating modes, tool usage, report format, scoring guide, compliance boundaries, and HTML report rules.

3. Install the MCP server dependencies: Python 3.10 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/), which provides `uvx`. Kiro CLI starts these MCP servers with `uvx` on first launch, at the pinned package versions in the agent config, so no other setup is needed:

   - `iac` (`uvx awslabs.aws-iac-mcp-server@1.0.25`): CloudFormation/CDK template validation and security rule checks
   - `aws-docs` (`uvx awslabs.aws-documentation-mcp-server@1.2.0`): AWS documentation search for SSB, SRB, and Well-Architected references
   - `aws-api` (`uvx --with mcp==1.30.0 awslabs.aws-api-mcp-server@1.5.4`): read-only AWS API calls for live configuration checks
   - `cloudwatch` (`uvx awslabs.cloudwatch-mcp-server@0.2.0`): CloudWatch alarm, log group, and metric inspection
   - `wa-security` (`uvx awslabs.well-architected-security-mcp-server@0.2.0`): Well-Architected Security Pillar assessment

   Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs.

   The `aws-api` server is launched with `--with 'mcp==1.30.0'` to work around an upstream packaging bug: the server declares `mcp>=1.23.0` with no upper bound, and `mcp` 2.x renamed `McpError` to `MCPError`, so a fresh install without the extra pin crashes on import with `ImportError: cannot import name 'McpError'`. `mcp` 1.30.0 is the version this agent was tested with.

   Upstream has announced that `awslabs.aws-api-mcp-server` is entering end of development and recommends moving to the AWS MCP Server ([migration guide](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md)). Version 1.5.4 tells the model about this in its tool descriptions, so the agent may mention the notice at the end of a session. The pinned version still works with this agent.

4. Set up credentials and permissions. The agent has two operating modes:

   - Mode 1, IaC Analysis: no AWS credentials needed. The agent reads your code and IaC files, validates templates, and checks them against security rules. Works for everyone.
   - Mode 2, Live Account Check: requires read-only AWS credentials (the `SecurityAudit` policy is recommended; `ReadOnlyAccess` also grants read access to data such as S3 object contents and DynamoDB items, which the agent would then be able to read and send to the model provider). The agent checks actual deployed configuration, monitoring, and security services. Much more thorough.

   For Mode 2, attach the `SecurityAudit` managed policy to the role you use. It is purpose-built for assessment without write access:

   ```bash
   aws iam attach-role-policy \
     --role-name <your-role> \
     --policy-arn arn:aws:iam::aws:policy/SecurityAudit
   ```

## Usage

1. Copy the agent into the project you want to check and launch it from there. Kiro CLI finds workspace agents in the `.kiro/agents/` folder of the directory you launch it from, and the agent reads files from that directory. Run this from the agent directory of step 1 in Agent Setup:

   ```bash
   cp -r .kiro /path/to/your-project/
   cd /path/to/your-project
   kiro-cli chat --agent production-readiness-checker
   ```

   If the project already has a `.kiro/` folder, the copy adds the agent's files next to the existing ones.

2. Ask a question. Example prompts:

   - "Is my project ready for production?" Expected output: a scored report (1-10) with critical/important findings across all 5 pillars, code fixes, and a recommended launch plan.
   - "What security issues should I fix before launching?" Expected output: security-specific findings ranked by severity with SSB references and fix snippets.
   - "Scan my live AWS account for production readiness issues" Expected output: a full 5-pillar assessment using live AWS data (security service status, actual alarm configuration, real backup settings, and the governance controls observed, such as CloudTrail and secrets handling).

## Example Output

Here's what a typical production readiness report looks like:

```
## Production Readiness Report

### Overall Score: 4/10, NOT READY (5 critical issues)

### 🔴 CRITICAL (fix before launch)

1. SECURITY: S3 bucket allows public access
   Impact: Data exposure risk
   Fix: Set blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL

2. RESILIENCE: Database single-AZ, no automated backups
   Impact: Data loss on AZ failure
   Fix:
   multiAz: true,
   backupRetention: cdk.Duration.days(7),

3. OBSERVABILITY: No CloudWatch alarms configured
   Impact: You won't know when things break
   Fix: Add alarms for CPU, memory, 5xx errors

4. SECURITY: Hardcoded AWS access key in source code (S6)
   Impact: Anyone with repository access can use the key
   Fix: Deactivate and rotate the key, then use an IAM role for the service

5. GOVERNANCE: Security group allows all inbound traffic (P3)
   Impact: Every port is reachable from the internet
   Fix: Allow only 443 on the load balancer and reference its security group from the app

### 🟡 IMPORTANT (fix within 2 weeks)

6. COST: db.m5.4xlarge for the database, oversized for a startup
7. RESILIENCE: No health checks on services

### 🟢 GOOD (already in place)

✅ VPC with private subnets
✅ Encryption at rest on the database

### 🎯 Recommended Launch Plan
1. Fix the 5 critical issues before launch (estimated: 2 hours)
2. Re-run the check and confirm no critical issue is open
3. Ship to production
4. Address important issues in first sprint
```

## Security and Data Handling

- Read-only by design. The agent inspects code, IaC, and live configuration, and reports findings. It never changes anything in your AWS account. Its AWS calls are reads: mostly `describe`, `list`, and `get` calls, plus CloudWatch metric reads and, if you approve them, CloudWatch Logs Insights queries, which read log data and are billed per GB scanned.
- The `aws-api` server runs with `READ_OPERATIONS_ONLY=true`, so mutating calls are refused at the MCP layer, not just discouraged in the prompt.
- Keep `READ_OPERATIONS_ONLY=true` in the `aws-api` server config. If you remove it, `@aws-api/call_aws` can also run AWS CLI commands that change your account, and only the approval prompt would stand between the agent and such a change.
- Every AWS CLI command (`@aws-api/call_aws`) asks for your approval before it runs, and so does every tool that is not on the agent's auto-approved list (for example Logs Insights queries and the network and storage encryption checks). Auto-approved: reading files inside your project folder, template validation and rule checks, documentation lookups, AWS command suggestions, CloudWatch alarm, log group and metric reads, and the security service status and findings reads. What the agent reads goes to the model provider. The approval prompt also offers to trust a tool for the rest of the session; if you accept that, later calls of that tool run without asking.
- File writes: the agent is instructed to save only the readiness report files you ask for, and reports can be saved in your project folder. Every write asks for your approval (`write` is not on the auto-approved tool list, and `requireConfirmation` is set). `.kiro/` and `.git/` in your project and hidden files and folders in your home directory (such as `~/.aws`, `~/.ssh`, and `~/.kiro`) are denied paths. Writes to other paths outside your project are not blocked by path; the approval prompt shows the path, so check it before you approve.
- File reads: File reads inside the folder you start the agent from run without asking (`toolsSettings.read.allowedPaths` is `./**`); a read of any other path asks for your approval first. Reads of hidden files and folders in your home directory (such as `~/.aws` and `~/.ssh`) are denied through `toolsSettings.read.deniedPaths`, within the limits described below. What the agent reads goes to the model provider. These read and write path rules match file paths and are not a sandbox, so another path to the same file can get past a denied path. The config also denies the macOS path forms `/System/Volumes/Data`, `/.vol`, `/.nofollow`, and `/.resolve`, which reach the same files, but other path forms may exist. A read through such a path still asks for your approval, because it is outside the folder you started the agent from, so check what the agent wants to read before you approve. If you trust `read` for the rest of the session at an approval prompt, reads outside that folder run without asking and only the denied paths still apply.
- Do not start this agent with `--trust-all-tools`: that flag skips every approval prompt and also the denied read and write paths.
- No self-modification: the agent's instructions forbid it to change its own configuration, prompt, context, or steering files, and `.kiro/` in your project is a denied write path.
- Every tool call the agent attempts, including calls you then decline, is appended (timestamp and tool name) to `~/.kiro/logs/production-readiness-checker-tools.log` by a `preToolUse` hook. Calls refused by a denied read or write path are rejected before the hook runs and are not logged. The hook never blocks the agent if it cannot write the log.
- Everything the agent reads (your files, templates, logs, and API responses) is treated as untrusted data, never as instructions. Content that tries to redirect the agent is reported as a suspicious finding.
- HTML reports: the agent's guidelines tell it to HTML-escape every value it takes from your files or tool output and to use no scripts and no external resources in the page. This is an instruction to the model, not a technical control, so review an HTML report before you share it.
- Pinned versions: every MCP server runs through `uvx` at a pinned package version. Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs.
- This agent interacts with your AWS account using your configured credentials. Review the permissions it requires and ensure they align with your organization's security policies.
- The agent does not store your AWS credentials. Its tools use them on your machine to sign read-only AWS API calls, and the agent is instructed never to repeat a credential value. What the agent reads during a session (your files, tool output, and AWS API responses, which can include account metadata such as account IDs, ARNs, and resource names) is sent to the model provider that Kiro CLI uses, so that the model can answer. Documentation lookups send their search terms to public AWS documentation endpoints. Apart from the report files you approve, the agent's own configuration writes only the local audit log described above (`~/.kiro/logs/production-readiness-checker-tools.log`, timestamps and tool names only). The MCP servers and `uvx` may keep their own local caches and logs. Kiro CLI itself can keep the conversation locally so you can resume it (`kiro-cli chat --resume`).
- Recommendations and outputs are generated by an AI model and may contain inaccuracies. Always verify suggestions before acting on them, especially for cost, security, or infrastructure changes.
- Use of this agent is subject to the [AWS Customer Agreement](https://aws.amazon.com/agreement/) and the [AWS Acceptable Use Policy](https://aws.amazon.com/aup/).
- The authors and AWS are not responsible for any costs, damages, or security issues arising from the use of this agent.

## Project Structure

```
production-readiness-checker/
├── .kiro/
│   ├── agents/
│   │   └── production-readiness-checker.json
│   └── context/
│       └── production-readiness-checker/
│           ├── checklist.md
│           └── guidelines.md
└── README.md
```

## License

This sample is licensed under the MIT-0 License, see the [LICENSE](https://github.com/aws-samples/sample-genai-startups/blob/main/LICENSE) file.

## Contributors

- Alexander Barge
