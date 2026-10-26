# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json, sys, re, collections
for f in sys.argv[1:]:
    txt = open(f).read()
    m = re.search(r"epoch=(\d+)", txt); kill = int(m.group(1)) if m else None
    for l in txt.splitlines():
        if not l.startswith("RESULT"): continue
        d = json.loads(l[7:]); k = kill - d["start_epoch"] if kill else None
        errs = collections.Counter(int(x) for x in d["error_at_s"])
        oks = collections.Counter(int(x) for x in (d.get("ok_at_s") or []))
        print(f"{f}: kill at t={k:.1f}s errors={d['errors']} kinds={d['error_kinds']} samples={d.get('error_samples')}")
        print("  sec: " + " ".join(f"{s}:{oks.get(s,0)}/{errs.get(s,0)}" for s in range(int(k)-3, int(k)+15)) + "   (ok/err by request start second)")
