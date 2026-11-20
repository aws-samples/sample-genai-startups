# Architecture Review

Architecture Review is a [Kiro CLI custom agent](https://kiro.dev/docs/cli/) that reviews agentic AI implementations against production best practices: point it at your agent code (system prompts, tool definitions, guardrails configs, observability setup) and get a structured review report with severity-ranked findings and a production readiness score.

> ⚠️ IMPORTANT DISCLAIMER
> This solution uses Generative AI. Always review all code, actions, and decisions before using in production environments.

It is an advisory review checklist. The agent reads your code and configuration and reports what it finds against a fixed checklist (`.kiro/context/architecture-review/checklist.md`). It does not implement, enforce, or test security controls, it does not run your agent, and a good score is not a security assessment, a penetration test, or a certification. Treat its findings as input for your own review.

Built for startup CTOs shipping their first AI agent to production, it covers security, cost guardrails, observability, responsible AI, and reliability across Bedrock Agents, Strands SDK, LangChain, and CrewAI. It can:

- Flag common security gaps in agent code: prompt injection exposure, overly broad tool permissions, missing output validation, PII leakage risks
- Analyze cost and reliability guardrails: loop circuit breakers, max iteration limits, cost alerts, retry strategies
- Assess observability posture: tracing, structured logging, CloudWatch integration, failure detection
- Evaluate responsible AI controls: Bedrock Guardrails, content filtering, denied topics, hallucination mitigation
- Generate a structured report with CRITICAL/WARNING/GOOD findings, fix suggestions, and a production readiness score (1-10)

## Install Kiro CLI

Follow the [Kiro CLI installation guide](https://kiro.dev/docs/getting-started/installation/) to install Kiro CLI on your platform, then verify the install:

```bash
kiro-cli --version
```

Kiro engine: this agent is tested on the default v2 agent engine of Kiro CLI 2.27.x. Do not start it with the v3 engine (`kiro-cli --v3` or `--agent-engine v3`): with automatic agent upgrade (`chat.enableAutoAgentUpgrade`) off, the v3 engine does not load this agent and falls back to the Kiro CLI default agent, and with it on, Kiro CLI converts the agent file in place without asking and runs the converted copy. On the v3 engine, the denied paths outside the project, including hidden files and folders in your home directory, do not apply to an agent installed in a project's `.kiro/` folder, the audit log hook does not run, and in the automatically converted file the approval for file writes no longer applies. If you use the v3 engine for anything, first run `kiro-cli settings chat.enableAutoAgentUpgrade false`, do not run `/upgrade-agent` on this agent or accept an upgrade offer, and if a `.bak` file next to the agent file shows that Kiro CLI already converted it, copy this agent's `.kiro/` folder from this repository again.

## Agent Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/aws-samples/sample-genai-startups.git
   cd sample-genai-startups/agentic-coding-library/agents/architecture-review
   ```

2. Review the agent configuration:

   - `.kiro/agents/architecture-review.json`: the agent definition, with its system prompt, MCP servers, tool list, auto-approved tools, read and write path rules, and audit log hooks.
   - `.kiro/context/architecture-review/checklist.md`: the production readiness checklist, grouped into security, cost guardrails, observability, responsible AI, and reliability, with a severity level per group.
   - `.kiro/context/architecture-review/guidelines.md`: how the agent conducts a review, when it uses each MCP server, the report format and scoring rules, the HTML report style and safe HTML rules, and what it must not do.

3. Install the MCP server dependencies: Python 3.10 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/), which provides `uvx`. Kiro CLI starts these MCP servers with `uvx` on first launch, at the pinned package versions in the agent config, so there is no other manual setup:

   - `agentcore` (`uvx awslabs.amazon-bedrock-agentcore-mcp-server@0.2.0`): AgentCore best practices, agent design patterns, deployment guidance.
   - `aws-docs` (`uvx awslabs.aws-documentation-mcp-server@1.2.0`): Bedrock Guardrails docs, security best practices, observability configuration.

   Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs.

4. Credentials and permissions: no AWS credentials are needed, because the agent reviews code, not live infrastructure.

   The AgentCore server starts with `AGENTCORE_ENABLE_TOOLS=none`, which leaves only its two documentation tools (`search_agentcore_docs` and `fetch_agentcore_doc`). Its runtime, gateway, browser, and code execution tools are not loaded, so the agent has no tool that calls AWS APIs in your account.

## Usage

1. Kiro CLI finds workspace agents in the `.kiro/agents/` folder of the directory you launch it from, and the agent reads files from that directory, so copy the agent into the root of the project that holds your agent code and launch it there. Run this from the agent directory of Agent Setup step 1:

   ```bash
   cp -r .kiro /path/to/your-project/
   cd /path/to/your-project
   kiro-cli chat --agent architecture-review
   ```

   If the project already has a `.kiro/` folder, the copy adds the agent's files next to the existing ones.

2. Try one of these prompts:

   - "Review my Bedrock Agent implementation in the `src/` directory for production readiness. Check security, cost guardrails, observability, and responsible AI." Expected output: a structured report with CRITICAL/WARNING/GOOD findings across all categories, fix suggestions with code snippets, and a production readiness score.
   - "Is my LangChain agent safe to deploy cost-wise? Does it have loop limits, spending alerts, and timeout configuration?" Expected output: cost and reliability findings with specific missing guardrails and recommended configurations.
   - "What observability should I add to my AI agent before going live? Review my current tracing and logging setup." Expected output: observability gaps with specific AWS service recommendations (X-Ray, CloudWatch) and configuration examples.

## Security and Data Handling

This agent is provided as a sample for educational and demonstration purposes only. It is not intended for production use without thorough review and testing in your own environment.

The agent is read-only and advisory by design. A few controls back that up:

- The system prompt confines it to review and reporting, forbids self-modification, and treats every config, prompt, and file it reviews as untrusted data rather than as instructions. Prompt injection found in reviewed material is reported as a finding instead of acted on.
- HTML reports: the agent's guidelines tell it to HTML-escape every value it takes from your files or tool output and to use no scripts and no external resources in the page. This is an instruction to the model, not a technical control, so review an HTML report before you share it.
- `write` is gated: every write asks for your approval (`write` is not on the auto-approved tool list, and `requireConfirmation` is set), and writes to `.kiro/` and `.git/` in your project and to hidden files and folders in your home directory (such as `~/.aws`, `~/.ssh`, and `~/.kiro`) are denied, so the agent cannot rewrite its own configuration or context. Reports can be saved in your project folder. The approval prompt also offers to trust a tool for the rest of the session; if you accept that for `write`, later writes run without asking.
- File reads inside the folder you start the agent from run without asking (`toolsSettings.read.allowedPaths` is `./**`); a read of any other path asks for your approval first. Reads of hidden files and folders in your home directory (such as `~/.aws` and `~/.ssh`) are denied through `toolsSettings.read.deniedPaths`, within the limits described below. What the agent reads goes to the model provider.
- These read and write path rules match file paths and are not a sandbox, so another path to the same file can get past a denied path. The config also denies the macOS path forms `/System/Volumes/Data`, `/.vol`, `/.nofollow`, and `/.resolve`, which reach the same files, but other path forms may exist. A read through such a path still asks for your approval, because it is outside the folder you started the agent from, so check what the agent wants to read before you approve. If you trust `read` for the rest of the session at an approval prompt, reads outside that folder run without asking and only the denied paths still apply.
- Do not start this agent with `--trust-all-tools`: that flag skips every approval prompt and also the denied read and write paths.
- Both MCP server packages are pinned to an exact version in the agent config. Only the top-level packages are pinned: their own dependencies are resolved by `uvx` at install time and can change between installs.
- A `preToolUse` hook appends a timestamped line naming each tool call the agent attempts, including calls you then decline, to `~/.kiro/logs/architecture-review-audit.log`. Calls refused by a denied read or write path are rejected before the hook runs and are not logged. An `agentSpawn` hook also writes a session start line to the same log. The log lives outside the repository, records only timestamps, tool names, and session starts, and never blocks a tool call if it cannot be written.
- This agent does not call AWS APIs in your account. It reads the local files you point it at and looks up public AWS documentation. File reads outside the folder you start it from ask for your approval, and reads of hidden files and folders in your home directory are denied.
- Its tools do not need AWS credentials. What the agent reads during a session (the files it reads and the documentation it looks up) is sent to the model provider that Kiro CLI uses, so that the model can answer. Documentation lookups send their search terms to public AWS documentation endpoints. Apart from the report files you approve, the agent's own configuration writes only the local audit log described above (`~/.kiro/logs/architecture-review-audit.log`, timestamps, tool names, and session starts only). The MCP servers and `uvx` may keep their own local caches and logs. Kiro CLI itself can keep the conversation locally so you can resume it (`kiro-cli chat --resume`).
- Recommendations and outputs are generated by an AI model and may contain inaccuracies. Always verify suggestions before acting on them, especially for cost, security, or infrastructure changes.
- Use of this agent is subject to the [AWS Customer Agreement](https://aws.amazon.com/agreement/) and the [AWS Acceptable Use Policy](https://aws.amazon.com/aup/).
- The authors and AWS are not responsible for any costs, damages, or security issues arising from the use of this agent.

## Project Structure

```
architecture-review/
├── .kiro/
│   ├── agents/
│   │   └── architecture-review.json
│   └── context/
│       └── architecture-review/
│           ├── checklist.md
│           └── guidelines.md
└── README.md
```

## License

This sample is licensed under the MIT-0 License, see the [LICENSE](https://github.com/aws-samples/sample-genai-startups/blob/main/LICENSE) file.

## Contributors

- Alexander Barge
