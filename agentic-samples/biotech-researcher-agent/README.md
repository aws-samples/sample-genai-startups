# Biotech Multi-Agent Research Assistant Demo

> **⚠️ Security Disclaimer:** This is sample code for demonstration purposes only — not production-ready. It should not be used for clinical decisions or deployed in a production environment without a thorough security review. All AI-generated outputs require expert human verification. See [SECURITY.md](SECURITY.md) for details.

Claude Agent SDK multi-agent orchestration for drug discovery hypothesis generation. An **opus** orchestrator delegates to three specialized subagents — streamed to your terminal or a browser UI in real time.

MCP tools (PubMed, ChEMBL, ClinicalTrials, bioRxiv, Open Targets) come from the [Anthropic Life Sciences Marketplace](https://github.com/anthropics/life-sciences) plugins installed in the Claude Code runtime. The application code has zero MCP configuration — tools are an infrastructure concern.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   Orchestrator (opus)                         │
│  Reads data → delegates → synthesizes report                 │
├──────────────┬────────────────────┬──────────────────────────┤
│              │                    │                           │
▼              ▼                    ▼                           │
┌────────────┐ ┌──────────────────┐ ┌────────────────────────┐ │
│  data-     │ │ literature-      │ │   hypothesis-          │ │
│  analyst   │ │  reviewer        │ │   generator            │ │
│  (sonnet)  │ │  (sonnet)        │ │    (opus)              │ │
│            │ │                  │ │                        │ │
│ pandas     │ │ PubMed           │ │ synthesizes data +     │ │
│ scipy      │ │ bioRxiv          │ │ lit into testable      │ │
│ seaborn    │ │ ClinicalTrials   │ │ hypotheses             │ │
│ ChEMBL     │ │                  │ │ ClinicalTrials         │ │
│ Open       │ │                  │ │ PubMed                 │ │
│ Targets    │ │                  │ │ Open Targets           │ │
└────────────┘ └──────────────────┘ └────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

MCP servers provided by Claude Code plugins (anthropics/life-sciences):
  PubMed · ChEMBL · ClinicalTrials · bioRxiv · Open Targets
```

## Setup

```bash
# One-time: install plugins + dependencies
./setup.sh

# Set your Anthropic API key
export ANTHROPIC_API_KEY="your-key-here"
```

## Run

### CLI

```bash
python run.py "your research question"
python run.py                          # interactive prompt
```

Color-coded streaming output:
- 🔵 **cyan** — data-analyst (stats + plots + ChEMBL + Open Targets)
- 🟢 **green** — literature-reviewer (PubMed + bioRxiv + ClinicalTrials)
- 🟣 **magenta** — synthesizer (novel hypotheses + target validation)

### Web UI

```bash
uvicorn app:app --reload
```

Open [http://localhost:8000](http://localhost:8000). Enter a research question and click **Run**. Agent events stream in real time via SSE with the same color-coded agent labels. Click **Stop** to cancel a run mid-flight.

## Dataset

`data/kras_inhibitor_assay.csv` — 30 rows of simulated KRAS inhibitor assay data (Sotorasib, Adagrasib, BRX-471). Assay types: enzymatic IC50, cellular IC50, combination therapy.

## Files

```
biotech-research/
├── run.py              # CLI orchestrator — streams agent reasoning to terminal
├── app.py              # FastAPI web UI backend (SSE streaming + cancel)
├── ui.html             # Browser frontend
├── agents.py           # Subagent definitions (roles, models, tool access)
├── setup.sh            # One-time: installs Claude Code plugins + Python deps
├── data/               # Experimental datasets
└── output/             # Generated plots + reports
```

## MCP Servers

Installed as Claude Code plugins from the [life-sciences marketplace](https://github.com/anthropics/life-sciences). No MCP config in application code — the SDK discovers tools from the runtime environment.

| Server | Provider | What it does |
|--------|----------|-------------|
| PubMed | NLM | Search biomedical literature, fetch abstracts |
| ChEMBL | deepsense.ai | Compound data, bioactivity, target info |
| ClinicalTrials | deepsense.ai | Search ClinicalTrials.gov registry |
| bioRxiv | deepsense.ai | Search bioRxiv/medRxiv preprints |
| Open Targets | OpenTargets | Drug target–disease association scoring |
