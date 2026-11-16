# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Leaf publisher: registers this cluster in the hub's Valkey registry and reports its ITL.

Every INTERVAL seconds it:
  - scrapes the leaf EPP (pool view: ready endpoints, queue, KV, streaming ITL histogram),
  - scrapes each model-server pod (per-pod ITL histogram and running requests),
  - fits ITL = a + b * running_per_pod over recent per-pod samples,
  - writes one JSON record to <PREFIX><CLUSTER> with a TTL, so a dead cluster ages out.
On SIGTERM it deletes its key, so a clean shutdown deregisters at once.
If the cluster has seen no traffic for PROBE_AFTER seconds it sends one small streaming
request through its own router, so the ITL signal never goes stale on an idle cluster.
"""
import json, os, re, signal, socket, sys, time
from collections import deque

import httpx
import redis

E = os.environ.get
CLUSTER, REGION = E("CLUSTER"), E("REGION", "")
PREFIX = E("PREFIX", "llmd:cluster:")
TTL, INTERVAL = int(E("TTL", "10")), float(E("INTERVAL", "2"))
WINDOW = int(E("WINDOW", "5"))  # intervals in the ITL window
EPP_METRICS = E("EPP_METRICS", "http://leaf-epp:9090/metrics")
ROUTER = E("ROUTER", "http://leaf-epp:80")
PODS_DNS, POD_PORT = E("PODS_DNS", "sim-pods"), E("POD_PORT", "8000")
GATEWAY_HOST, GATEWAY_PORT, METRICS_PORT = E("GATEWAY_HOST"), E("GATEWAY_PORT", "80"), E("METRICS_PORT", "9090")
MAX_SEQS = float(E("MAX_SEQS", "16"))
MODEL = E("MODEL", "Qwen/Qwen3-32B")
PROBE_AFTER = float(E("PROBE_AFTER", "15"))
FIT_SAMPLES = int(E("FIT_SAMPLES", "300"))

rdb = redis.Redis(host=E("REDIS_HOST"), port=int(E("REDIS_PORT", "6379")), ssl=E("REDIS_TLS", "true") == "true",
                  socket_timeout=2, socket_connect_timeout=2)
key = PREFIX + CLUSTER
http = httpx.Client(timeout=3)
WRITER = socket.gethostname()
# Delete the key only if this pod wrote it last. During a rolling update the new publisher has
# already re-registered by the time the old one exits; a blind DEL would drop the cluster.
DEL_IF_MINE = rdb.register_script(
    "local v = redis.call('GET', KEYS[1]) "
    "if v and cjson.decode(v)['writer'] == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0")


def bye(*_):
    try:
        if E("DEREGISTER_ON_EXIT", "true") == "true":
            n = DEL_IF_MINE(keys=[key], args=[WRITER])
            print("deregistered" if n else "key owned by a newer publisher; left it", key, flush=True)
    finally:
        sys.exit(0)


signal.signal(signal.SIGTERM, bye)
signal.signal(signal.SIGINT, bye)


def scrape(url):
    return http.get(url).text


def series(text, name):
    """Sum of all series of a metric (gauge or counter)."""
    return sum(float(v) for v in re.findall(rf"^{re.escape(name)}(?:\{{[^}}]*\}})? ([0-9.eE+-]+)$", text, re.M))


def gateway_ip():
    # Internal NLB IPs are stable for the NLB's life. The hub's Envoy needs an IP, not a name.
    return sorted(socket.gethostbyname_ex(GATEWAY_HOST)[2])[0]


def pod_ips():
    try:
        return sorted(set(socket.gethostbyname_ex(PODS_DNS)[2]))
    except socket.gaierror:
        return []


def fit(samples):
    # Real vLLM ITL has spikes (a prefill or a preemption stalls every decode in the batch for one
    # step). Least squares chases them, so drop samples above 3x the median before fitting.
    if len(samples) >= 3:
        med = sorted(y for _, y in samples)[len(samples) // 2]
        samples = [s for s in samples if s[1] <= 3 * med]
    n = len(samples)
    if n < 3:
        return None, None
    xs, ys = [s[0] for s in samples], [s[1] for s in samples]
    mx, my = sum(xs) / n, sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    if vx < 1e-6:
        return my, 0.0
    b = max(0.0, sum((x - mx) * (y - my) for x, y in samples) / vx)
    return my - b * mx, b


def probe():
    body = {"model": MODEL, "prompt": "probe", "max_tokens": 16, "stream": True}
    try:
        with http.stream("POST", f"{ROUTER}/v1/completions", json=body, timeout=30) as r:
            for _ in r.iter_lines():
                pass
    except Exception as e:
        print("probe failed", e, flush=True)


def main():
    gw = gateway_ip()
    prev_pool, prev_pod = None, {}
    win = deque(maxlen=WINDOW)          # (d_sum, d_count) of pool ITL per interval
    pod_win = {}                         # ip -> deque of (d_sum, d_count)
    samples = deque(maxlen=FIT_SAMPLES)  # (running_per_pod, itl_ms)
    last_traffic = time.time()
    last_itl = last_best = 0.0           # hold the last measured value through quiet windows
    itl_name = "llm_d_epp_request_streaming_itl_seconds"
    while True:
        t0 = time.time()
        try:
            m = scrape(EPP_METRICS)
            pool = (series(m, itl_name + "_sum"), series(m, itl_name + "_count"))
            if prev_pool:
                win.append((pool[0] - prev_pool[0], pool[1] - prev_pool[1]))
            prev_pool = pool
            ready = series(m, "llm_d_epp_ready_endpoints")
            waiting = series(m, "llm_d_epp_average_queue_size")
            kv = series(m, "llm_d_epp_average_kv_cache_utilization")

            best, running = None, []
            for ip in pod_ips():
                pm = scrape(f"http://{ip}:{POD_PORT}/metrics")
                cur = (series(pm, "vllm:inter_token_latency_seconds_sum"), series(pm, "vllm:inter_token_latency_seconds_count"),
                       series(pm, "vllm:num_requests_running"))
                running.append(cur[2])
                if ip in prev_pod:
                    ds, dc = cur[0] - prev_pod[ip][0], cur[1] - prev_pod[ip][1]
                    pw = pod_win.setdefault(ip, deque(maxlen=WINDOW))
                    pw.append((ds, dc))
                    if dc > 0:
                        samples.append(((cur[2] + prev_pod[ip][2]) / 2, 1000 * ds / dc))
                    s, c = sum(x[0] for x in pw), sum(x[1] for x in pw)
                    if c > 0:
                        best = min(best, 1000 * s / c) if best is not None else 1000 * s / c
                prev_pod[ip] = cur

            s, c = sum(x[0] for x in win), sum(x[1] for x in win)
            if win and win[-1][1] > 0:
                last_traffic = time.time()
            if c > 0:
                last_itl = 1000 * s / c
            if best:
                last_best = best
            a, b = fit(list(samples))
            rec = {"cluster": CLUSTER, "region": REGION, "ts": time.time(), "writer": WRITER,
                   "gateway": f"{gw}:{GATEWAY_PORT}", "metrics": f"{gw}:{METRICS_PORT}",
                   "ready": ready, "max_seqs": MAX_SEQS, "waiting": waiting, "kv": kv,
                   "itl_ms": round(last_itl, 3), "best_pod_itl_ms": round(last_best, 3),
                   "running_per_pod": round(sum(running) / max(len(running), 1), 3),
                   "itl_a_ms": round(a, 3) if a is not None else 0, "itl_b_ms": round(b, 4) if b is not None else 0,
                   "fit_n": len(samples)}
            rdb.set(key, json.dumps(rec), ex=TTL)
            open("/tmp/ready", "w").close()  # readiness: first publish done
            print(json.dumps(rec), flush=True)
        except Exception as e:  # keep going; the TTL deregisters us if this persists
            print("publish failed:", repr(e), flush=True)
        if time.time() - last_traffic > PROBE_AFTER:
            probe()
            last_traffic = time.time()
        time.sleep(max(0, INTERVAL - (time.time() - t0)))


if __name__ == "__main__":
    main()
