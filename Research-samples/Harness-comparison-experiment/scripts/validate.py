"""Batch validation for Bazaar-80: does the harness gap actually show up?

Runs N matches for each seller condition along the ladder (RAW -> DEFAULT -> GOOD
on each model, plus large+BAD) against a fixed buyer, then aggregates the metrics
that matter for the booth scoreboard:

  - deal rate                 (did they converge at all?)
  - mean seller surplus       (claiming: did the seller win the split?)
  - mean seller claim %        (share of the constant pie the seller captured)
  - mean surplus destroyed     (the cost of a no-deal; zero-sum, so no efficiency
                                story -- every CLOSED deal is Pareto-optimal)
  - invalid-offer count        (format / execution-alignment failures)
  - mean seller tool calls     (is the GOOD/DEFAULT pipeline actually firing?)
  - mean cost per match

Use this to tune utility tables / prompts until the gap is reliable, then to
generate the bundled fallback traces. No deploy required -- runs on the local
Strands executor.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from typing import Callable, Dict, List

from bazaar80.harness import (
    LARGE_MODEL,
    LocalHarnessExecutor,
    SMALL_MODEL,
    bad_harness,
    default_harness,
    good_harness,
    raw_harness,
)
from bazaar80.negotiate import MatchResult, negotiate


@dataclass
class CellAgg:
    label: str
    n: int
    deal_rate: float
    seller_surplus: float
    buyer_surplus: float
    seller_claim_pct: float
    surplus_destroyed: float
    seller_invalid: float
    seller_tool_calls: float
    cost: float


def _seller_tool_calls(r: MatchResult) -> int:
    return sum(len(e.get("tool_calls", [])) for e in r.events if e["side"] == "seller")


def _save_trace(scenario_id: str, label: str, idx: int,
                seller_cfg, buyer_cfg, r: MatchResult) -> None:
    """Persist a full match trace for replay / publishing."""
    out_dir = Path(__file__).resolve().parent.parent / "traces" / (scenario_id or "default")
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "scenario": scenario_id or "default",
        "cell": label,
        "seller": {"kind": seller_cfg.kind.value, "model": seller_cfg.model_id},
        "buyer": {"kind": buyer_cfg.kind.value, "model": buyer_cfg.model_id},
        "outcome": r.outcome,
        "rounds": r.rounds,
        "final_deal": r.final_deal.as_dict() if r.final_deal else None,
        "score": r.score,
        "invalid_offers": r.invalid_offers,
        "total_cost_usd": r.total_cost_usd,
        "events": r.events,
    }
    path = out_dir / f"{label.replace('+', '_')}_{idx:02d}.json"
    path.write_text(json.dumps(record, indent=2, default=str))


def _existing_count(scenario_id: str, label: str) -> int:
    """How many trace files already exist for this cell (so --append can resume
    numbering past them instead of overwriting from 00)."""
    out_dir = Path(__file__).resolve().parent.parent / "traces" / (scenario_id or "default")
    prefix = label.replace("+", "_") + "_"
    return len(list(out_dir.glob(prefix + "[0-9]*.json"))) if out_dir.exists() else 0


def _aggregate(label: str, results: List[MatchResult]) -> CellAgg:
    n = len(results)
    mean = lambda xs: round(statistics.mean(xs), 2) if xs else 0.0
    deals = [r for r in results if r.outcome == "deal"]
    return CellAgg(
        label=label,
        n=n,
        deal_rate=round(100.0 * len(deals) / n, 1) if n else 0.0,
        seller_surplus=mean([r.score["seller_surplus"] for r in results]),
        buyer_surplus=mean([r.score["buyer_surplus"] for r in results]),
        seller_claim_pct=mean([r.score["seller_claim_pct"] for r in results]),
        surplus_destroyed=mean([r.score["surplus_destroyed"] for r in results]),
        seller_invalid=mean([r.invalid_offers["seller"] for r in results]),
        seller_tool_calls=mean([_seller_tool_calls(r) for r in results]),
        cost=round(sum(r.total_cost_usd for r in results), 4),
    )


# Each cell: a label and a factory returning (seller_cfg, buyer_cfg).
def _cells() -> Dict[str, Callable[[], tuple]]:
    # Fixed buyer = small RAW (Nova-2-Lite, no harness): cheap, consistent, and
    # BEATABLE, so the only thing that moves the outcome is the SELLER's
    # model x harness. (A Sonnet buyer was too strong and flattened every cell.)
    buyer = lambda: raw_harness("buyer", SMALL_MODEL)
    return {
        # The LADDER, run on each model: no harness -> pre-built scaffold ->
        # engineered harness. RAW->DEFAULT isolates "turn the agent framework on"
        # (tools + loop + memory); DEFAULT->GOOD isolates "engineer the config"
        # (ToM prompt + validate gate + state hints). Same config object throughout.
        "small+RAW":     lambda: (raw_harness("seller", SMALL_MODEL),     buyer()),
        "small+DEFAULT": lambda: (default_harness("seller", SMALL_MODEL), buyer()),
        "small+GOOD":    lambda: (good_harness("seller", SMALL_MODEL),    buyer()),
        "large+RAW":     lambda: (raw_harness("seller", LARGE_MODEL),     buyer()),
        "large+DEFAULT": lambda: (default_harness("seller", LARGE_MODEL), buyer()),
        "large+GOOD":    lambda: (good_harness("seller", LARGE_MODEL),    buyer()),
        # large model + the BAD guardrail -> expect a DROP, ideally below small+GOOD
        "large+BAD":     lambda: (bad_harness("seller", LARGE_MODEL),     buyer()),
    }


def run(n: int, max_rounds: int, verbose: bool, scenario_id: str = None,
        save_traces: bool = False, append: bool = False, target: int = 0) -> None:
    from bazaar80 import game
    from bazaar80.scenarios import get_scenario

    scenario = None
    buyer_style = ""
    if scenario_id:
        scenario = get_scenario(scenario_id)
        game.set_batnas(scenario.seller_batna, scenario.buyer_batna)
        buyer_style = scenario.buyer_style
        max_rounds = scenario.max_rounds
        print(f"SCENARIO: {scenario.name} -- {scenario.tagline}")
        print(f"  teaches: {scenario.teaches}")
        print(f"  ZOPA: seller_batna={game.SELLER_BATNA:g} buyer_batna={game.BUYER_BATNA:g} "
              f"divisible={game.DIVISIBLE_SURPLUS:g} rounds={max_rounds}")

    executor = LocalHarnessExecutor()
    cells = _cells()
    aggs: List[CellAgg] = []

    for label, factory in cells.items():
        results: List[MatchResult] = []
        # --append: resume file numbering past existing traces (only pay the delta)
        base = _existing_count(scenario_id, label) if (save_traces and (append or target)) else 0
        # --target N: top THIS cell up to N total (idempotent/resumable); else run n.
        todo = max(0, target - base) if target else n
        tag = (f"  (target {target}, have {base}, +{todo})" if target
               else (f"  (n={n}, appending after {base})" if base else f"  (n={n})"))
        print(f"\n=== cell: {label}{tag} ===")
        saved = 0   # successful saves this run -> contiguous index after `base`
        for i in range(todo):
            seller_cfg, buyer_cfg = factory()
            if buyer_style:
                buyer_cfg.system_prompt += "\n\nOPPONENT STYLE:\n" + buyer_style
            t0 = time.time()
            # Resilience: a transient Bedrock/network blip (e.g. connection reset)
            # must not abort the whole sweep. Retry a few times, then skip the match.
            r = None
            for attempt in range(4):
                try:
                    r = negotiate(seller_cfg, buyer_cfg, executor,
                                  max_rounds=max_rounds, verbose=verbose)
                    break
                except Exception as e:
                    wait = 2 * (attempt + 1)
                    print(f"    ! match {i+1}/{todo} error ({type(e).__name__}); "
                          f"retry {attempt+1}/3 in {wait}s")
                    if attempt == 3:
                        print(f"    !! giving up on match {i+1}/{todo}: {e}")
                    else:
                        time.sleep(wait)
            if r is None:
                continue
            results.append(r)
            if save_traces:
                _save_trace(scenario_id, label, base + saved, seller_cfg, buyer_cfg, r)
                saved += 1
            tc = _seller_tool_calls(r)
            print(f"  match {i+1}/{todo}: {r.outcome:<7} "
                  f"seller={r.score['seller_surplus']:>6.0f} "
                  f"claim={r.score['seller_claim_pct']:>5.0f}% "
                  f"destroyed={r.score['surplus_destroyed']:>5.0f} "
                  f"inval={r.invalid_offers['seller']} stools={tc} "
                  f"${r.total_cost_usd:.4f} ({time.time()-t0:.1f}s)")
        if results:
            aggs.append(_aggregate(label, results))

    # Comparison table
    print("\n" + "=" * 110)
    hdr = (f"{'cell':<12} {'deal%':>6} {'seller':>8} {'claim%':>7} {'buyer':>8} "
           f"{'destroy':>8} {'invalid':>8} {'s_tools':>8} {'cost$':>8}")
    print(hdr)
    print("-" * 110)
    for a in aggs:
        print(f"{a.label:<12} {a.deal_rate:>6.1f} {a.seller_surplus:>8.0f} "
              f"{a.seller_claim_pct:>7.1f} {a.buyer_surplus:>8.0f} "
              f"{a.surplus_destroyed:>8.0f} {a.seller_invalid:>8.2f} "
              f"{a.seller_tool_calls:>8.2f} {a.cost:>8.4f}")
    print("=" * 110)

    # Headline reads: dependency-on-harness and bad-harness degradation.
    by = {a.label: a for a in aggs}
    def delta(hi: str, lo: str, field: str = "seller_surplus"):
        if hi in by and lo in by:
            return getattr(by[hi], field) - getattr(by[lo], field)
        return None

    print("\nHEADLINE READS (zero-sum: claiming + closing):")

    # The ladder: no harness -> pre-built scaffold -> engineered, per model.
    def _ladder(model: str) -> None:
        raw, dflt, good = f"{model}+RAW", f"{model}+DEFAULT", f"{model}+GOOD"
        if not {raw, dflt, good} <= by.keys():
            return
        d1 = delta(dflt, raw)    # scaffold-on lift
        d2 = delta(good, dflt)   # engineering lift
        print(f"  {model.upper()} ladder: "
              f"RAW {by[raw].seller_surplus:.0f} "
              f"-> DEFAULT {by[dflt].seller_surplus:.0f} ({d1:+.0f}, scaffold on) "
              f"-> GOOD {by[good].seller_surplus:.0f} ({d2:+.0f}, engineered)  "
              f"deal% {by[raw].deal_rate:.0f}/{by[dflt].deal_rate:.0f}/{by[good].deal_rate:.0f}")

    _ladder("small")
    _ladder("large")

    d_small = delta("small+GOOD", "small+RAW")
    d_large = delta("large+GOOD", "large+RAW")
    if d_small is not None and d_large is not None:
        print(f"  => small model is {'MORE' if d_small > d_large else 'NOT more'} dependent on the harness "
              f"(total RAW->GOOD lift: small {d_small:+.0f} vs large {d_large:+.0f})")
    if {"large+BAD", "large+RAW"} <= by.keys():
        b, r = by["large+BAD"], by["large+RAW"]
        print(f"  BAD guardrail on LARGE: {b.seller_surplus - r.seller_surplus:+.0f} seller surplus, "
              f"deal% {r.deal_rate:.0f}->{b.deal_rate:.0f}, destroyed {r.surplus_destroyed:.0f}->{b.surplus_destroyed:.0f}")
    if {"small+GOOD", "large+BAD"} <= by.keys():
        g, b = by["small+GOOD"], by["large+BAD"]
        print(f"  MONEY SHOT: small+GOOD seller {g.seller_surplus:.0f} ({g.seller_claim_pct:.0f}% claim, "
              f"{g.deal_rate:.0f}% deals) vs large+BAD seller {b.seller_surplus:.0f} "
              f"({b.seller_claim_pct:.0f}% claim, {b.deal_rate:.0f}% deals)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=3, help="matches per cell")
    ap.add_argument("--max-rounds", type=int, default=7)
    ap.add_argument("--scenario", type=str, default=None,
                    help="scenario id: tight_window | anchor_war | fine_print | marathon")
    ap.add_argument("--save-traces", action="store_true", help="write per-match JSON traces")
    ap.add_argument("--append", action="store_true",
                    help="resume trace numbering after existing files (don't overwrite "
                         "from 00); use to grow the random-replay pool cheaply")
    ap.add_argument("--target", type=int, default=0,
                    help="top EACH cell up to this many total traces (idempotent / "
                         "resumable: only runs the per-cell delta). Overrides -n.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    run(args.n, args.max_rounds, args.verbose, args.scenario, args.save_traces,
        args.append, args.target)
