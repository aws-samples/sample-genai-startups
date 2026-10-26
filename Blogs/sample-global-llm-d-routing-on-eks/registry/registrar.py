# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Hub registrar: renders the hub's clusters.yaml ConfigMap from the Valkey registry.

Every INTERVAL seconds it reads all <PREFIX>* records and writes one endpoint per live
cluster into the mc-hub-clusters ConfigMap. The hub EPP watches that file. A cluster whose
key expired (no publisher heartbeat) drops out on the next pass. If the registry is
unreachable the ConfigMap is left as it is, so the hub keeps routing on the last good list.
"""
import json, os, time

import redis
import yaml
from kubernetes import client, config

E = os.environ.get
PREFIX, INTERVAL = E("PREFIX", "llmd:cluster:"), float(E("INTERVAL", "1"))
NS, CM = E("NAMESPACE", "llm-d"), E("CONFIGMAP", "mc-hub-clusters")
# Keep a cluster in the file until its key has been missing this long. The hub plugin already
# filters a missing cluster within a second, so the file can lag. This stops a registry restart
# (empty, then refilled over one publish interval) from rewriting the file with a partial list.
GRACE = float(E("GRACE", "15"))
seen = {}  # cluster -> (endpoint entry, last time its key was present)

rdb = redis.Redis(host=E("REDIS_HOST"), port=int(E("REDIS_PORT", "6379")), ssl=E("REDIS_TLS", "true") == "true",
                  socket_timeout=2, socket_connect_timeout=2)
config.load_incluster_config()
core = client.CoreV1Api()


def render():
    keys = sorted(rdb.scan_iter(PREFIX + "*", count=100))
    now = time.time()
    for k, v in zip(keys, rdb.mget(keys) if keys else []):
        if not v:
            continue
        r = json.loads(v)
        host, port = r["gateway"].rsplit(":", 1)
        mhost, mport = r["metrics"].rsplit(":", 1)
        seen[r["cluster"]] = ({"name": r["cluster"], "address": host, "port": port,
                               "labels": {"metricsAddress": mhost, "metricsPort": mport, "region": r.get("region", "")}}, now)
    for name in [n for n, (_, t) in seen.items() if now - t > GRACE]:
        del seen[name]
    eps = [seen[n][0] for n in sorted(seen)]
    return yaml.safe_dump({"endpoints": eps}, sort_keys=False)


def main():
    last = None
    while True:
        try:
            doc = render()
            if doc != last:
                core.patch_namespaced_config_map(CM, NS, {"data": {"clusters.yaml": doc}})
                names = [e["name"] for e in yaml.safe_load(doc)["endpoints"]]
                print(time.strftime("%H:%M:%S"), "clusters ->", names, flush=True)
                last = doc
        except Exception as e:
            print("render failed, keeping last list:", repr(e), flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
