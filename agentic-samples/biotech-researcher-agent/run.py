#!/usr/bin/env python3
"""
Biotech-Research Orchestrator
==============================
Thin runner that wires agents + MCP tools and streams reasoning to terminal.

Usage:  python run.py "your research question"
        python run.py                          # interactive prompt
"""

import asyncio, sys, random
from pathlib import Path

from claude_agent_sdk import query
from claude_agent_sdk.types import (
    AssistantMessage, ClaudeAgentOptions, ResultMessage,
    TextBlock, ThinkingBlock, ToolUseBlock,
)
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

DIM, BOLD, RST = "\033[2m", "\033[1m", "\033[0m"

TOOLS = [
    "Read", "Write", "Bash", "Glob", "Grep",
    "mcp__pubmed__*", "mcp__chembl__*", "mcp__clinicaltrials__*",
    "mcp__biorxiv__*", "mcp__opentargets__*",
]


def build_prompt(question: str) -> str:
    return (
        f"You are a senior research scientist. Data files: {DATA_DIR}  Output dir: {OUTPUT_DIR}\n"
        f"You have tools for: file I/O, bash, PubMed, ChEMBL, ClinicalTrials.gov, bioRxiv, Open Targets.\n"
        f"Reason step by step: analyze data, search literature, then synthesize testable hypotheses.\n"
        f"Every citation must use real PMIDs/NCT IDs. Never fabricate references.\n"
        f"IMPORTANT: All outputs are AI-generated and require expert human review before use in any research or clinical decisions.\n\n"
        f"RESEARCH QUESTION: {question}"
    )


async def main():
    question = " ".join(sys.argv[1:]) or input("Research question: ").strip()
    if not question:
        return print("No question provided.")
    if len(question) > 2000:
        return print("Error: Question exceeds maximum length of 2000 characters.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"\n{BOLD}{'='*60}\n  Biotech-Research — Multi-Agent Research Demo\n{'='*60}{RST}")
    print(f"{DIM}Q: {question[:100]}{RST}\n")

    agent = None  # track which subagent is active
    max_retries = 5

    for attempt in range(max_retries):
        try:
            async for msg in query(
                prompt=build_prompt(question),
                options=ClaudeAgentOptions(
                    model="opus",
                    allowed_tools=TOOLS,
                    # SECURITY: bypassPermissions is for demo/sandboxed use only.
                    # For production, use permission_mode="requireApproval".
                    permission_mode="bypassPermissions",
                    max_turns=80,
                    cwd=str(ROOT),
                    thinking={"type": "enabled", "budget_tokens": 10000},
                ),
            ):
                # ── Reasoning & tool use ─────────────────────────────
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ThinkingBlock) and block.thinking.strip():
                            lines = block.thinking.strip().splitlines()
                            print(f"{DIM}💭 {lines[0]}{RST}", flush=True)
                            for ln in lines[1:8]:
                                print(f"{DIM}   {ln}{RST}", flush=True)
                            if len(lines) > 8:
                                print(f"{DIM}   … ({len(lines)-8} more){RST}", flush=True)

                        elif isinstance(block, TextBlock) and block.text.strip():
                            for ln in block.text.splitlines():
                                print(ln, flush=True)

                        elif isinstance(block, ToolUseBlock):
                            inp = block.input or {}
                            detail = next((f' → "{inp[k]}"' for k in ("query","compound_name","pmid","doi","target") if k in inp), "")
                            print(f"{DIM}🔧 {block.name}{detail}{RST}", flush=True)

                # ── Final result ─────────────────────────────────────
                elif isinstance(msg, ResultMessage):
                    print(f"\n{BOLD}{'='*60}\n  RESEARCH BRIEF\n{'='*60}{RST}\n")
                    print(msg.result or "(no output)")
                    if msg.total_cost_usd:
                        print(f"\n{DIM}Cost: ${msg.total_cost_usd:.4f} | Turns: {msg.num_turns} | {msg.duration_ms/1000:.1f}s{RST}")

            break  # success — exit retry loop

        except Exception as e:
            if "529" in str(e) or "Overloaded" in str(e):
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"{DIM}⏳ API overloaded (attempt {attempt+1}/{max_retries}), retrying in {wait:.1f}s…{RST}")
                await asyncio.sleep(wait)
            else:
                raise

    # List generated files
    plots = list(OUTPUT_DIR.glob("*.png"))
    if plots:
        print(f"\n{BOLD}Generated:{RST}")
        for p in plots:
            print(f"  📊 {p.name}")


if __name__ == "__main__":
    asyncio.run(main())
