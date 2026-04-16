# Biotech Research Assistant Demo

> **⚠️ Security Disclaimer:** This is sample code for demonstration purposes only — not production-ready. It should not be used for clinical decisions or deployed in a production environment without a thorough security review. All AI-generated outputs require expert human verification. See [SECURITY.md](SECURITY.md) for details.

Two implementations of a drug discovery research assistant built with the Claude Agent SDK, both streaming to your terminal or a browser UI in real time.

MCP tools (PubMed, ChEMBL, ClinicalTrials, bioRxiv, Open Targets) come from the [Anthropic Life Sciences Marketplace](https://github.com/anthropics/life-sciences) plugins, loaded explicitly via `SdkPluginConfig` in `ClaudeAgentOptions`.

## Two approaches, one codebase

### Multi-agent (prior)
An `opus` orchestrator delegates to three specialised subagents — `data-analyst` (sonnet), `literature-reviewer` (sonnet), and `synthesizer` (opus) — each with a defined role, prompt, and scoped tool access. Useful when you need parallel workstreams or a clear audit trail of which agent produced which output.

### Harness (current)
A single `opus` agent with access to all tools. No role decomposition — the model reasons through data analysis, literature search, and hypothesis synthesis in one coherent thread. Less scaffolding, fewer handoff failure points, and better cross-domain reasoning for integrative tasks.

```
┌─────────────────────────────────────────────────────┐
│                  Single agent (opus)                 │
│                                                      │
│  file I/O · bash · PubMed · ChEMBL · ClinicalTrials │
│            bioRxiv · Open Targets                    │
│                                                      │
│  Reasons step by step: load data → search lit →     │
│  synthesize testable hypotheses                      │
└─────────────────────────────────────────────────────┘
```

## Setup

```bash
# One-time: install plugins + dependencies
./setup.sh

# Set your Anthropic API key (or use your plan to login to Claude Code in the terminal)
export ANTHROPIC_API_KEY="your-key-here"
```

## Run

### CLI

```bash
python run.py "your research question"
python run.py                          # interactive prompt
```

### Web UI

```bash
uvicorn app:app --reload
```

Open [http://localhost:8000](http://localhost:8000). Enter a research question and click **Run**. Agent events stream in real time via SSE. Click **Stop** to cancel mid-flight.

## Dataset

`data/kras_inhibitor_assay.csv` — 30 rows of simulated KRAS inhibitor assay data (Sotorasib, Adagrasib, BRX-471). Assay types: enzymatic IC50, cellular IC50, combination therapy.

## Files

```
biotech-researcher-agent/
├── run.py              # CLI — streams agent reasoning to terminal
├── app.py              # FastAPI web UI backend (SSE streaming + cancel)
├── ui.html             # Browser frontend
├── agents.py           # Empty (harness approach); subagent defs in git history
├── setup.sh            # One-time: installs Claude Code plugins + Python deps
├── data/               # Experimental datasets
└── output/             # Generated plots + reports
```

## MCP Servers

Installed via `setup.sh` as Claude Code plugins from the [life-sciences marketplace](https://github.com/anthropics/life-sciences). Loaded into the SDK explicitly via `plugins=PLUGINS` in `ClaudeAgentOptions`.

| Server | Provider | What it does |
|--------|----------|-------------|
| PubMed | NLM | Search biomedical literature, fetch abstracts |
| ChEMBL | deepsense.ai | Compound data, bioactivity, target info |
| ClinicalTrials | deepsense.ai | Search ClinicalTrials.gov registry |
| bioRxiv | deepsense.ai | Search bioRxiv/medRxiv preprints |
| Open Targets | OpenTargets | Drug target–disease association scoring |
