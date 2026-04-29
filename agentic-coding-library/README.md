# Agentic Coding Library

A curated collection of steering documents, prompts, agents, hooks, and powers that turn generic AI coding assistants into AWS domain experts. Built by the AWS Startup team based on real customer scenarios, these assets are designed to solve the problems startups actually face — shipping fast with small teams, making the right architectural choices early, and avoiding costly rework as you scale.

## Why This Exists

Startups move fast with lean engineering teams. AI coding assistants can be a force multiplier, but out of the box they lack deep context about AWS-specific conventions, service nuances, and the trade-offs that matter most at the startup stage — cost efficiency, speed to production, and foundations that won't collapse at scale.

This library bridges that gap. Every asset is shaped by patterns we see across startup customers: choosing the right compute and database services for your stage, writing infrastructure as code that grows with you, implementing security and observability without slowing down, and avoiding over-engineering when simplicity wins.

## Repository Structure

```
agentic-coding-library/
├── steering/       # AWS development standards and guidelines
├── prompts/        # Reusable instructions for common AWS tasks
├── agents/         # Custom agent configurations with AWS expertise
├── hooks/          # Automation hooks for AWS workflows
└── kiro-powers/    # Kiro Power bundles packaging tools and AWS knowledge
```

### Steering

Guidelines that teach your coding assistant AWS conventions — how to structure CDK apps, use the AWS SDK correctly, follow Well-Architected patterns, handle IAM policies, and more.

### Prompts

Task-specific instructions for common AWS development workflows: writing CloudFormation templates, building Lambda functions, configuring API Gateway, setting up observability, and similar tasks.

### Agents

Custom agent configurations that act as AWS specialists — architecture advisors, security reviewers, infrastructure builders, and cost optimization guides.

### Hooks

Automation hooks that integrate AWS-aware checks into your development workflow, triggered on events like file saves or commits.

### Kiro Powers

Complete bundles that package MCP server configurations, steering files, and tools into a single unit focused on specific AWS domains.

## Supported Coding Assistants

| Assistant | How to Use |
|---|---|
| **Kiro IDE / Kiro CLI** | Copy files into your project's `.kiro/` directory or `~/.kiro/` for global use |
| **Claude Code** | Adapt steering docs as `CLAUDE.md` or `.claude/rules/` files |

## Getting Started

1. Browse the directories above to find resources relevant to your project
2. Read the README in the root of each folder for setup and usage instructions
3. Customize as needed for your specific use case

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed guidelines.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../LICENSE) file.
