# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Streaming load generator for the hub.

Sends OpenAI-style streaming completions at a fixed concurrency, records TTFT, ITL and
decode throughput per request, and counts how many requests each leaf served (delta of the
leaf EPP's llm_d_epp_request_total). Prints one machine-readable RESULT line at the end.

Env: TARGET, MODEL, CONCURRENCY, REQUESTS, MAX_TOKENS, PROMPT_WORDS, CLUSTERS_FILE, TAG
"""
import asyncio, json, os, random, re, statistics, time

import httpx
import yaml

TARGET = os.environ.get("TARGET", "http://hub-epp.llm-d.svc")
MODEL = os.environ.get("MODEL", "Qwen/Qwen3-32B")
CONC = int(os.environ.get("CONCURRENCY", "32"))
N = int(os.environ.get("REQUESTS", "400"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "256"))
PROMPT_WORDS = int(os.environ.get("PROMPT_WORDS", "300"))
CLUSTERS_FILE = os.environ.get("CLUSTERS_FILE", "/etc/clusters/clusters.yaml")
TAG = os.environ.get("TAG", "run")
DURATION = float(os.environ.get("DURATION", "0"))  # if set, run for this many seconds instead of N requests
ERR_SAMPLES = []
WORDS = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike".split()


def leaves():
    try:
        with open(CLUSTERS_FILE) as f:
            eps = yaml.safe_load(f)["endpoints"]
        return {e["name"]: f'{e["labels"]["metricsAddress"]}:{e["labels"].get("metricsPort", "9090")}' for e in eps}
    except Exception as e:  # loadgen still works without per-leaf counts
        print("no clusters file:", e)
        return {}


async def served_counts(client, lv):
    out = {}
    for name, addr in lv.items():
        try:
            r = await client.get(f"http://{addr}/metrics", timeout=5)
            m = re.findall(r"^llm_d_epp_request_total\{[^}]*\} ([0-9.e+]+)$", r.text, re.M)
            out[name] = sum(float(x) for x in m)
        except Exception:
            out[name] = None
    return out


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


T0 = time.perf_counter()


async def one(client, i, res):
    prompt = " ".join(random.choice(WORDS) for _ in range(PROMPT_WORDS))
    body = {"model": MODEL, "prompt": f"{i} {prompt}", "max_tokens": MAX_TOKENS, "stream": True,
            "stream_options": {"include_usage": True}}
    t0 = time.perf_counter(); first = None; last = None; gaps = []; chunks = 0
    try:
        async with client.stream("POST", f"{TARGET}/v1/completions", json=body, timeout=600) as r:
            if r.status_code != 200:
                body = (await r.aread())[:200]
                if len(ERR_SAMPLES) < 5:
                    ERR_SAMPLES.append(f"{r.status_code} {dict(r.headers).get('server')} {body!r}")
                res.append({"err": r.status_code, "at": t0 - T0}); return
            async for line in r.aiter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                d = json.loads(line[6:])
                if not d.get("choices") or not d["choices"][0].get("text"):
                    continue
                now = time.perf_counter()
                if first is None:
                    first = now
                else:
                    gaps.append(now - last)
                last = now; chunks += 1
    except Exception as e:
        res.append({"err": type(e).__name__, "at": t0 - T0}); return
    if first is None:
        res.append({"err": "no-tokens", "at": t0 - T0}); return
    res.append({"at": t0 - T0, "ttft": first - t0, "e2e": last - t0, "tokens": chunks,
                "itl": statistics.mean(gaps) if gaps else None})


async def main():
    global T0
    lv = leaves()
    limits = httpx.Limits(max_connections=CONC * 2, max_keepalive_connections=CONC * 2)
    async with httpx.AsyncClient(limits=limits) as client:
        before = await served_counts(client, lv)
        res, q = [], asyncio.Queue()
        for i in range(N):
            q.put_nowait(i)

        async def worker():
            i = 0
            while (time.perf_counter() - T0 < DURATION) if DURATION else not q.empty():
                await one(client, q.get_nowait() if not DURATION else i, res)
                i += 1

        t0 = T0 = time.perf_counter()
        start_epoch = time.time()
        await asyncio.gather(*(worker() for _ in range(CONC)))
        wall = time.perf_counter() - t0
        await asyncio.sleep(2)
        after = await served_counts(client, lv)

    ok = [r for r in res if "err" not in r]
    errs = [r["err"] for r in res if "err" in r]
    itl = [r["itl"] for r in ok if r["itl"]]
    ttft = [r["ttft"] for r in ok]
    toks = sum(r["tokens"] for r in ok)
    split = {k: (after[k] - before[k]) if after.get(k) is not None and before.get(k) is not None else None for k in lv}
    out = {
        "tag": TAG, "start_epoch": round(start_epoch, 1), "requests": N, "ok": len(ok), "errors": len(errs), "error_kinds": sorted(set(map(str, errs))),
        "concurrency": CONC, "max_tokens": MAX_TOKENS, "wall_s": round(wall, 2),
        "throughput_tok_s": round(toks / wall, 1),
        "ttft_ms": {p: round(1000 * pct(ttft, p), 1) for p in (50, 90, 99)} if ttft else None,
        "itl_ms": {p: round(1000 * pct(itl, p), 2) for p in (50, 90, 99)} if itl else None,
        "served_by": split,
        "error_at_s": sorted(round(r["at"], 1) for r in res if "err" in r)[:2000],
        "error_samples": ERR_SAMPLES,
        "ok_at_s": sorted(round(r["at"], 1) for r in res if "err" not in r) if DURATION else None,
    }
    print("RESULT " + json.dumps(out), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
