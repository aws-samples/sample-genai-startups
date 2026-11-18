# AWS Cost Calculator Agent

An AI-powered conversational agent that helps you estimate AWS costs for your project. Built using [Kiro CLI](https://kiro.dev) with Claude and the AWS API MCP server.

## What It Does

Describe your project in plain English, and this agent will:

1. **Understand your requirements** — Ask targeted questions about your architecture, scale, and availability needs
2. **Identify AWS services** — Propose the right services based on your use case, with cost-effective defaults
3. **Clarify configurations** — Prompt for specifics that significantly impact cost (instance types, storage tiers, reserved vs on-demand)
4. **Generate a cost estimate** — Produce a detailed breakdown with monthly/annual totals
5. **Provide a Calculator URL** — Give you a reproducible estimate in the AWS Pricing Calculator

## Example Conversation

```
You: I'm building a SaaS platform for project management. We expect about 5,000 
     users in the first year, with a React frontend and Node.js API backend. 
     We need a database and file storage for attachments.

Agent: Great! Let me ask a few clarifying questions:
       1. What's your expected request volume? (e.g., average concurrent users, 
          API calls per minute)
       2. How much file storage do you anticipate? (average attachment size × uploads/month)
       3. Do you need multi-AZ high availability for production, or is single-AZ acceptable?

You: Maybe 500 concurrent users at peak, 100 requests/min average. 
     Attachments maybe 50GB/month growing. Single-AZ is fine for now.

Agent: Based on your requirements, here's what I'd suggest:
       - **Compute**: ECS Fargate (2 tasks, 0.5 vCPU, 1GB each) for the API
       - **Database**: RDS PostgreSQL (db.t4g.medium, 50GB gp3, single-AZ)
       - **Storage**: S3 Standard for attachments
       - **CDN**: CloudFront for the React frontend
       - **Load Balancer**: ALB in front of ECS
       
       A few more questions:
       1. Would you like Redis/ElastiCache for session caching?
       2. Do you need a CI/CD pipeline (CodePipeline/CodeBuild)?
       ...
```

## Prerequisites

- [Kiro CLI](https://kiro.dev) installed
- AWS credentials configured (read-only access to Pricing APIs is sufficient)
- Python 3.10+ (for `uvx` to run the MCP server)
- [uv](https://docs.astral.sh/uv/) package manager installed
- Node.js 18+ (for Playwright MCP server)

## Quick Start

```bash
# Clone this repository
git clone <repo-url>
cd costcalculatoragent

# Start the agent (Playwright MCP auto-installs via npx)
kiro-cli chat --agent cost-calculator-agent
```

Then describe your project and the agent will guide you through the estimation process.

## Project Structure

```
.
├── .kiro/
│   ├── agents/
│   │   └── cost-calculator-agent.json   # Agent definition (model, tools, permissions)
│   ├── context/
│   │   └── cost-calculator-agent/
│   │       └── guidelines.md            # Behavioral rules & conversation flow
│   ├── hooks/
│   │   └── preToolUse.sh               # Security: blocks non-pricing AWS API calls
│   └── mcp.json                         # MCP server config (AWS API + Playwright)
├── .gitignore
├── README.md
└── cost-estimate.md                     # Generated estimate report
```

## How It Works

1. **Kiro CLI** loads the agent configuration and connects to Claude Sonnet 4.6
2. **AWS API MCP Server** provides live access to AWS Pricing APIs (`pricing:GetProducts`, `pricing:DescribeServices`)
3. **Guidelines** define a 9-step sequential conversation flow:
   - Step 1: Region selection
   - Step 2: Infrastructure topology (AZs, environments)
   - Steps 3-7: Service layers (Compute → Database → Storage → Networking → Supporting)
   - Step 8: Pricing model
   - Step 9: Final output + Calculator URL
4. **Playwright MCP Server** automates the AWS Pricing Calculator browser UI to generate a shareable public URL with all services pre-populated (no API key needed)

## Calculator URL Generation (Playwright)

Instead of asking you to manually recreate the estimate, the agent uses the [Playwright MCP server](https://github.com/anthropics/playwright-mcp) to:

1. Open https://calculator.aws/ in a headless browser
2. Add each service with the exact parameters you confirmed
3. Fill in every field (instance type, storage, region, count, etc.)
4. Click "Share" to generate a public link
5. Return the shareable URL to you

This happens automatically — no API keys or extra setup needed. Playwright runs locally via `npx @playwright/mcp@latest`.

**Output:** A URL like `https://calculator.aws/#/estimate?id=...` that anyone can open to see the full estimate.

## Security

- **Read-only**: The agent never creates, modifies, or deletes AWS resources
- **Scoped APIs**: Only pricing-related AWS APIs are called (pricing, ce, sts)
- **File restrictions**: Can only write to `cost-estimate.md` and `reports/` directory
- **Self-protection**: Cannot modify its own configuration in `.kiro/`

## Cost Optimization Tips the Agent Considers

- Graviton (ARM) instances over x86 where compatible (~20% savings)
- gp3 EBS volumes over gp2 (better price-performance)
- S3 Intelligent-Tiering for unpredictable access patterns
- Spot instances for fault-tolerant workloads (up to 90% savings)
- HTTP API Gateway over REST API for simple use cases (70% cheaper)
- Reserved Instances / Savings Plans for steady-state workloads (up to 72% savings)
- NAT Gateway alternatives (VPC endpoints, S3 gateway endpoints)

## Limitations

- Pricing is looked up in real-time but may not reflect all discounts (EDPs, private pricing)
- Data transfer costs are estimated based on stated patterns — actual costs depend on traffic shape
- The generated Calculator URL provides a starting point; complex configurations may need manual adjustment
- Does not account for AWS credits, support plans, or marketplace subscriptions

## Contributing

Contributions welcome! Areas for improvement:
- Additional service coverage (more niche services)
- Better heuristics for architecture recommendations
- Regional pricing comparison features
- Terraform/CloudFormation cost estimation from IaC files

## License

MIT
