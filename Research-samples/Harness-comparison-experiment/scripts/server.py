"""Bazaar-80 backend (optional) -- serve the front end + stream LIVE negotiations.

The booth front end works fully offline in replay mode (web/traces.js). This
backend adds the "run it for real" path: it serves the static page and exposes a
streaming endpoint that runs an actual Bedrock negotiation and pushes each move
to the browser as it happens (Server-Sent Events).

Run:
    pip install -r requirements-server.txt
    python server.py              # http://127.0.0.1:8080
Needs AWS creds with Bedrock access in us-west-2 (same as validate.py).

Endpoints:
    GET /                      -> the front end (web/index.html)
    GET /traces.js             -> bundled replay data
    GET /api/scenarios         -> list of scenarios + cells
    GET /api/run?scenario=&cell=  -> SSE stream of live negotiation events
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import json
import threading

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from bazaar80 import game
from bazaar80.harness import (
    LARGE_MODEL,
    SMALL_MODEL,
    LocalHarnessExecutor,
    bad_harness,
    default_harness,
    good_harness,
    raw_harness,
)
from bazaar80.negotiate import negotiate
from bazaar80.scenarios import SCENARIOS_BY_ID, get_scenario

WEB = PROJECT_ROOT / "web"   # scripts/ -> project root
app = FastAPI(title="Bazaar-80")
_executor = LocalHarnessExecutor()
_game_lock = threading.Lock()  # game.set_batnas mutates module globals

# cell label -> seller factory. The ladder (RAW -> DEFAULT -> GOOD) on each
# model, plus large+BAD. Buyer is always a fixed small RAW opponent.
_SELLER = {
    "small+RAW":     lambda: raw_harness("seller", SMALL_MODEL),
    "small+DEFAULT": lambda: default_harness("seller", SMALL_MODEL),
    "small+GOOD":    lambda: good_harness("seller", SMALL_MODEL),
    "large+RAW":     lambda: raw_harness("seller", LARGE_MODEL),
    "large+DEFAULT": lambda: default_harness("seller", LARGE_MODEL),
    "large+GOOD":    lambda: good_harness("seller", LARGE_MODEL),
    "large+BAD":     lambda: bad_harness("seller", LARGE_MODEL),
}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/v2")
def index_v2():
    # Alternate UI (LOWBALL-only, decluttered). Same /api/run + /traces.js paths.
    return FileResponse(WEB / "index_v2.html")


@app.get("/traces.js")
def traces_js():
    f = WEB / "traces.js"
    if not f.exists():
        return JSONResponse({"error": "run bundle_traces.py first"}, status_code=404)
    return FileResponse(f, media_type="application/javascript")


@app.get("/api/scenarios")
def scenarios():
    return {sid: {"name": s.name, "tagline": s.tagline, "teaches": s.teaches,
                  "cells": list(_SELLER.keys())}
            for sid, s in SCENARIOS_BY_ID.items()}


@app.get("/api/run")
async def run(request: Request, scenario: str, cell: str = "small+GOOD"):
    if cell not in _SELLER:
        return JSONResponse({"error": f"unknown cell {cell}"}, status_code=400)
    try:
        scen = get_scenario(scenario)
    except KeyError:
        return JSONResponse({"error": f"unknown scenario {scenario}"}, status_code=400)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    def worker():
        # Mutating BATNAs is global; serialize live runs.
        with _game_lock:
            game.set_batnas(scen.seller_batna, scen.buyer_batna)
            seller_cfg = _SELLER[cell]()
            buyer_cfg = raw_harness("buyer", SMALL_MODEL)
            buyer_cfg.system_prompt += "\n\nOPPONENT STYLE:\n" + scen.buyer_style

            def on_event(ev):
                loop.call_soon_threadsafe(queue.put_nowait, ("event", ev))

            try:
                result = negotiate(seller_cfg, buyer_cfg, _executor,
                                   max_rounds=scen.max_rounds, on_event=on_event)
                payload = {"outcome": result.outcome, "rounds": result.rounds,
                           "final_deal": result.final_deal.as_dict() if result.final_deal else None,
                           "score": result.score, "cost_usd": result.total_cost_usd}
                loop.call_soon_threadsafe(queue.put_nowait, ("done", payload))
            except Exception as e:  # surface failures to the UI
                loop.call_soon_threadsafe(queue.put_nowait, ("error", {"message": str(e)}))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    async def stream():
        # tell the client which fighters are in play
        yield _sse("meta", {"scenario": scen.name, "cell": cell})
        while True:
            item = await queue.get()
            if item is SENTINEL:
                break
            kind, data = item
            yield _sse(kind, data)
            if await request.is_disconnected():
                break

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)
