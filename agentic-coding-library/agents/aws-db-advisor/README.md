# aws-db-advisor

A [Kiro CLI custom agent](https://kiro.dev/docs/cli/) that helps startup developers pick and run the right AWS database. It answers the question every developer hits — "What database should I use?" — then follows up with cost estimates, growth paths, high-availability guidance, and migration plans.

The agent covers the AWS database portfolio (Aurora, RDS, DynamoDB, ElastiCache/Valkey, OpenSearch, Neptune, MemoryDB, Timestream, DocumentDB, DSQL) and knows when to recommend each one based on app type, scale, and access patterns. It guides AI/ML use cases through vector database selection — from pgvector for small workloads through OpenSearch and S3 Vectors at scale. It advises on high availability and disaster recovery at every level, from free multi-AZ storage replication through multi-region active-active with cost trade-offs. It also handles heterogeneous migrations (Oracle to RDS, MSSQL to Aurora PostgreSQL) and major version upgrade planning with failure recovery strategies. It uses the AWS Knowledge MCP server to look up live documentation and check regional availability for questions beyond its bundled context files.

> ⚠️ IMPORTANT DISCLAIMER
> This solution uses Generative AI. Always review all code, actions, and decisions before using in production environments.

## Capabilities

- Database selection — maps your app type and scale to the right AWS database, with ballpark costs and a growth path
- Vector and AI — guides pgvector, OpenSearch, Neptune, MemoryDB, and DocumentDB selection for RAG, semantic search, and GraphRAG
- High availability and disaster recovery — multi-AZ through multi-region active-active, with cost trade-offs
- Cost optimisation — Savings Plans, Reserved Instances, I/O-Optimised storage decisions, scale-to-zero configurations
- Connectivity — RDS Proxy, Lambda patterns, connection pooling, local write forwarding
- Migration — RDS to Aurora, Oracle to RDS (DMS), MSSQL to Aurora PostgreSQL, cross-account replication
- Operations — PostgreSQL performance tuning, partitioning, CDC/zero-ETL to analytics, major version upgrades
- Multi-tenant architecture — schema isolation, bin-packing, pool fragmentation
- Live documentation lookup via the AWS Knowledge MCP server

## Model requirements

This agent was developed and tested on Claude Sonnet 4.6+. Lower models may ignore the bundled context files and fall back to training data, producing incorrect answers — particularly for facts that changed after their training cutoff (for example, Aurora Serverless v2 zero-ACU auto-pause). Pin a capable model for reliable results.

## Install Kiro CLI

Install the Kiro CLI and verify it is on your PATH:

```bash
curl -fsSL https://cli.kiro.dev/install | bash
kiro-cli --version
```

## Agent Setup

1. Clone this repository and change into the agent directory:

   ```bash
   git clone <repository-url>
   cd aws-db-advisor
   ```

2. Review the agent configuration before installing:
   - `.kiro/agents/aws-db-advisor.json` — agent definition (prompt, MCP servers, tools, resources)
   - `POWER.md` — the agent prompt (persona, behaviour rules, topic routing)
   - `.kiro/context/aws-db-advisor/*.md` — 15 reference files covering architecture, cost, HA/DR, migration, and operations

3. Install prerequisites:
   - `unzip` (required by the Kiro CLI installer; preinstalled on macOS, `sudo apt-get install -y unzip` on Debian/Ubuntu)
   - [Node.js](https://nodejs.org/) 18+ — `npx` ships with Node and launches the MCP server

4. Run the installer:

   ```bash
   ./install.sh                  # Install as a Kiro agent (default)
   ./install.sh claude           # Install as a Claude Code Skill
   ./install.sh all              # Install both targets
   ```

   The default mode copies the agent config and context files to `~/.kiro/agents/aws-db-advisor/`. Uninstall with `./install.sh uninstall` (or `uninstall-agent` / `uninstall-claude`).

   To add the database advisory capability to an agent you already have rather than creating a new one:

   ```bash
   ./install.sh agent --agent my-existing-agent
   ```

   This merges the advisor's context files, MCP servers, resources, and tools into the target agent's configuration without touching its prompt, hooks, or description.

5. The `aws-knowledge-mcp-server` MCP server is launched automatically via `npx` on first run (it connects to the public AWS Knowledge MCP endpoint). No credentials or additional setup are required.

### Claude Code

The `claude/` directory contains the same advisor packaged as a Claude Code Skill. Install it with `./install.sh claude`. In Claude Code you **must** invoke the skill with `/aws-db-advisor` before asking your database question, otherwise Claude Code answers from general knowledge and may be wrong for facts that changed after its training cutoff.

## Usage

Launch the agent from any directory:

```bash
kiro-cli chat --agent aws-db-advisor
```

Example prompts:

- "I'm building a SaaS project management tool. What database should I use on AWS?"
- "I'm running Aurora PostgreSQL Serverless v2 with a single writer. Is my database highly available?"
- "I need my app to survive a complete AWS region failure. What's the cheapest way to do multi-region DR?"
- "I'm building a RAG chatbot that needs to search through documents. What database should I use?"
- "I'm using AWS Lambda with Aurora PostgreSQL Serverless v2 and hitting connection limits when Lambda scales up. What should I do?"

## Project Structure

```
aws-db-advisor/
├── POWER.md                          # Agent prompt: persona, behaviour, topic routing
├── install.sh                        # Installer (Kiro agent / Claude Code Skill)
├── LICENSE                           # MIT-0
├── README.md
├── claude/
│   └── aws-db-advisor.md             # Claude Code Skill definition
└── .kiro/
    ├── agents/
    │   └── aws-db-advisor.json       # Agent configuration
    └── context/
        └── aws-db-advisor/           # 15 reference files (architecture, cost, HA/DR, migration, ops)
```

## License

MIT-0

## Contributors

- Orlando Andico
