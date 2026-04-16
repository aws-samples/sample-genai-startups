#!/usr/bin/env bash
# Install life-sciences MCP plugins into Claude Code.
# Run once per environment (dev machine, container image, etc.)
set -euo pipefail

echo "Adding anthropics/life-sciences marketplace…"
claude plugin marketplace add anthropics/life-sciences

echo "Installing life-sciences MCP servers…"
claude plugin install pubmed@life-sciences
claude plugin install chembl@life-sciences
claude plugin install clinical-trials@life-sciences
claude plugin install biorxiv@life-sciences
claude plugin install open-targets@life-sciences

echo "Installing life-sciences skills…"
claude plugin install clinical-trial-protocol@life-sciences

echo "Installing Python dependencies…"
pip install claude-agent-sdk pandas matplotlib seaborn scipy

echo "✓ Done. Run:  python run.py \"your research question\""
