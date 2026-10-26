# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import sys, json
for l in open(sys.argv[1]):
    l = l.strip().removeprefix("RESULT ")
    if not l.startswith("{"):
        print(l); continue
    d = json.loads(l)
    t, i = d["ttft_ms"] or {}, d["itl_ms"] or {}
    print(f'{d["tag"]:30} ok={d["ok"]:4} err={d["errors"]} tok/s={d["throughput_tok_s"]:7} '
          f'ttft50={t.get("50")} ttft90={t.get("90")} itl50={i.get("50")} itl90={i.get("90")} split={d["served_by"]}')
