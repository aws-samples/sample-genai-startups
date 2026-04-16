#!/usr/bin/env python3
"""
Biotech-Research Web UI
===============
Thin FastAPI wrapper around the agent orchestrator.
Streams agent events via SSE, supports cancel mid-run.

    uvicorn app:app --reload
"""

import asyncio, json, logging, secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from claude_agent_sdk import query
from claude_agent_sdk.types import (
    AssistantMessage, ClaudeAgentOptions, ResultMessage,
    TextBlock, ThinkingBlock, ToolUseBlock, SdkPluginConfig,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

MAX_QUESTION_LEN = 2000
MAX_CONCURRENT_RUNS = 5

TOOLS = [
    "Read", "Write", "Bash", "Glob", "Grep",
    "mcp__pubmed__*", "mcp__chembl__*", "mcp__clinicaltrials__*",
    "mcp__biorxiv__*", "mcp__opentargets__*",
]

PLUGINS = [
    SdkPluginConfig(type="local", path="pubmed@life-sciences"),
    SdkPluginConfig(type="local", path="chembl@life-sciences"),
    SdkPluginConfig(type="local", path="clinical-trials@life-sciences"),
    SdkPluginConfig(type="local", path="biorxiv@life-sciences"),
    SdkPluginConfig(type="local", path="open-targets@life-sciences"),
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


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def run_stream(question: str, cancel: asyncio.Event):
    OUTPUT_DIR.mkdir(exist_ok=True)

    try:
        async for msg in query(
            prompt=build_prompt(question),
            options=ClaudeAgentOptions(
                model="opus",
                allowed_tools=TOOLS,
                plugins=PLUGINS,
                # SECURITY: bypassPermissions is for demo/sandboxed use only.
                # For production, use permission_mode="requireApproval".
                permission_mode="bypassPermissions",
                max_turns=80,
                cwd=str(ROOT),
                thinking={"type": "enabled", "budget_tokens": 10000},
            ),
        ):
            if cancel.is_set():
                yield sse("cancelled", {})
                return

            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ThinkingBlock) and block.thinking.strip():
                        yield sse("thinking", {"text": block.thinking.strip()})
                    elif isinstance(block, TextBlock) and block.text.strip():
                        yield sse("text", {"text": block.text})
                    elif isinstance(block, ToolUseBlock):
                        inp = block.input or {}
                        detail = next((inp[k] for k in ("query", "compound_name", "pmid", "doi", "target") if k in inp), "")
                        yield sse("tool", {"name": block.name, "detail": detail})

            elif isinstance(msg, ResultMessage):
                yield sse("result", {
                    "text": msg.result or "",
                    "cost": msg.total_cost_usd,
                    "turns": msg.num_turns,
                    "duration_ms": msg.duration_ms,
                })

    except asyncio.CancelledError:
        yield sse("cancelled", {})
    except Exception as e:
        logger.exception("Run failed")
        yield sse("error", {"message": "Internal error — check server logs."})

    yield sse("done", {})


@app.get("/", response_class=HTMLResponse)
async def index():
    return (ROOT / "ui.html").read_text()


@app.get("/stream")
async def stream(question: str = Query(..., max_length=MAX_QUESTION_LEN)):
    if len(runs) >= MAX_CONCURRENT_RUNS:
        raise HTTPException(status_code=429, detail="Too many concurrent runs")

    run_id = secrets.token_urlsafe(16)
    cancel = asyncio.Event()

    async def generator():
        yield sse("run_id", {"id": run_id})
        async for chunk in run_stream(question, cancel):
            yield chunk
        runs.pop(run_id, None)

    runs[run_id] = cancel
    return StreamingResponse(generator(), media_type="text/event-stream")


@app.post("/cancel/{run_id}")
async def cancel(run_id: str):
    if run_id in runs:
        runs[run_id].set()
        return {"status": "cancelling"}
    return {"status": "not_found"}
