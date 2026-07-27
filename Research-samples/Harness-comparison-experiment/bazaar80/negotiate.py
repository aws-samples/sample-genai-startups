"""Alternating-offer negotiation loop for Bazaar-80.

Drives a SELLER config against a BUYER config, turn by turn, until someone
accepts a standing offer, someone walks, or the round budget is exhausted. Emits
a structured trace (scratchpad, tool calls, offers, invalid-offer glitches) that
the scoreboard, batch metrics, and the front-end trace viewer all consume.

The same loop runs every harness condition; only the HarnessConfig changes. That
is the experiment.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from bazaar80.game import Deal, score_outcome
from bazaar80.harness import HarnessConfig, HarnessKind, LocalHarnessExecutor, Move
from bazaar80.tools import batna, calc_utility, snap_to_legal


def _render_offer(deal: Optional[Deal]) -> str:
    if deal is None:
        return "(no concrete terms)"
    return f"unit_price={deal.unit_price:g}, payment_terms={deal.payment_terms}"


def _public_line(side: str, move: Move) -> str:
    """What the OTHER party sees: the message plus any concrete offer/decision."""
    who = side.upper()
    if move.action == "OFFER":
        return f"{who} offers: {_render_offer(move.deal)}. {move.message}"
    if move.action == "ACCEPT":
        return f"{who} ACCEPTS the standing offer. {move.message}"
    if move.action == "WALK":
        return f"{who} walks away. {move.message}"
    return f"{who} says: {move.message or '(unclear, malformed response)'}"


def _own_line(move: Move) -> str:
    """What the agent sees fed back as ITS OWN prior turn (the `assistant` role).

    Critical: an agent must see its own past turns as the first-person JSON move
    it actually emitted -- NOT the third-person `_public_line` narration ("BUYER
    offers: ..."). Feeding the narration back trains a small model to imitate that
    surface form and abandon the JSON contract (it starts emitting prose like
    "BUYER offers: unit_price=7 ...", which fails to parse, freezes its standing
    offer, and stalls the negotiation). Reconstructing the canonical move object
    reinforces the OUTPUT_CONTRACT instead."""
    if move.action in {"OFFER", "ACCEPT", "WALK"}:
        obj: Dict = {"action": move.action}
        if move.deal is not None:
            obj["deal"] = move.deal.as_dict()
        obj["message"] = move.message
        return json.dumps(obj)
    # Malformed turn with no usable action: feed the message in first person,
    # WITHOUT the "SIDE says:" prefix that would otherwise compound the mimicry.
    return move.message or "(no valid move)"


def _build_messages(my_side: str, history: List[Dict], state_note: str = "") -> List[Dict]:
    """Build this agent's Bedrock Converse view from the public history.

    Opponent turns -> role 'user'; own turns -> role 'assistant'. Must begin with
    a user message, so we seed one when the agent opens. `state_note` (used only
    by the engineered harness) appends a structured state reminder.
    """
    messages: List[Dict] = []
    for ev in history:
        if ev["side"] == my_side:
            # The agent's OWN turn: feed back the first-person JSON move it made,
            # so it keeps reinforcing the output contract (see _own_line).
            messages.append({"role": "assistant", "content": [{"text": ev["own_line"]}]})
        else:
            # The opponent's turn: the public, third-person narration.
            messages.append({"role": "user", "content": [{"text": ev["line"]}]})

    if not messages or messages[0]["role"] != "user":
        seed = ("You are opening the negotiation. Make your first move now."
                if not messages else
                "Continue the negotiation. It is your turn to respond.")
        messages.insert(0, {"role": "user", "content": [{"text": seed}]})
    if state_note:
        messages.append({"role": "user", "content": [{"text": state_note}]})
    # Collapse consecutive same-role messages (Converse requires alternation).
    return _coalesce(messages)


def _coalesce(messages: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for m in messages:
        if out and out[-1]["role"] == m["role"]:
            out[-1]["content"].extend(m["content"])
        else:
            out.append({"role": m["role"], "content": list(m["content"])})
    return out


@dataclass
class MatchResult:
    final_deal: Optional[Deal]
    score: Dict
    events: List[Dict] = field(default_factory=list)
    rounds: int = 0
    total_cost_usd: float = 0.0
    invalid_offers: Dict[str, int] = field(default_factory=lambda: {"seller": 0, "buyer": 0})
    outcome: str = "no_deal"   # "deal" | "walk" | "no_deal" (timeout)


def negotiate(
    seller_cfg: HarnessConfig,
    buyer_cfg: HarnessConfig,
    executor: Optional[LocalHarnessExecutor] = None,
    *,
    max_rounds: int = 5,
    verbose: bool = False,
    on_event=None,
) -> MatchResult:
    """Run one full negotiation. Seller opens; they alternate up to max_rounds each.

    If `on_event` is given, it is called with each trace event as it happens
    (used by the live-streaming backend)."""
    executor = executor or LocalHarnessExecutor()
    cfgs = {"seller": seller_cfg, "buyer": buyer_cfg}

    history: List[Dict] = []                       # [{side, line}]
    events: List[Dict] = []                        # structured trace
    standing: Dict[str, Optional[Deal]] = {"seller": None, "buyer": None}
    invalid = {"seller": 0, "buyer": 0}
    total_cost = 0.0
    final_deal: Optional[Deal] = None
    outcome = "no_deal"

    order = ["seller", "buyer"]
    done = False
    rounds_played = 0

    for rnd in range(max_rounds):
        rounds_played = rnd + 1
        for side in order:
            opp = "buyer" if side == "seller" else "seller"
            cfg = cfgs[side]
            # The engineered harness gets structured per-turn STATE -- the facts it
            # needs to converge and close before the round budget runs out (the
            # loop exit). These are facts, not instructions: how many rounds remain,
            # the value of the standing offer, and the walkaway floor. HOW to weigh
            # them is left to the agent's reasoning under its negotiation skill --
            # we deliberately do NOT script accept/hold/counter per case. The
            # unengineered configs stay blind to this state.
            state_note = ""
            if cfg.validate_gate:
                opp_offer = standing[opp]
                rounds_left = max_rounds - rnd
                bits = [f"NEGOTIATION STATE (facts; apply your negotiation policy): "
                        f"round {rnd + 1} of {max_rounds}, {rounds_left} round(s) left "
                        f"before the deal is lost. Your walkaway floor is {batna(side):.0f}."]
                if opp_offer is not None:
                    val = calc_utility(opp_offer, side)
                    bits.append(f"The {opp}'s current standing offer is worth {val:.0f} to you.")
                else:
                    bits.append(f"The {opp} has not made a concrete offer yet.")
                state_note = " ".join(bits)
            messages = _build_messages(side, history, state_note)
            move = executor.run_turn(cfg, messages)
            total_cost += move.cost_usd

            ev = {
                "round": rnd, "side": side, "kind": cfg.kind.value,
                "action": move.action, "message": move.message,
                "scratchpad": move.scratchpad, "tool_calls": move.tool_calls,
                "invalid": move.invalid, "cost_usd": move.cost_usd,
                "usage": move.usage,
            }

            # Handle invalid / malformed output: keep the game alive but record it.
            if move.invalid or move.action is None:
                invalid[side] += 1
                if move.deal is not None:               # parsed a deal but illegal -> snap
                    snapped = snap_to_legal(move.deal)
                    move = Move(action="OFFER", deal=snapped, message=move.message,
                                parse_ok=True, invalid=True, scratchpad=move.scratchpad,
                                tool_calls=move.tool_calls, raw_text=move.raw_text,
                                usage=move.usage, cost_usd=move.cost_usd)
                    ev.update({"action": "OFFER", "snapped_deal": snapped.as_dict(),
                               "glitch": "illegal_offer_snapped"})
                else:
                    ev.update({"glitch": "malformed_no_offer"})
                    events.append(ev)
                    if on_event: on_event(ev)
                    history.append({"side": side, "line": _public_line(side, move),
                                    "own_line": _own_line(move)})
                    if verbose:
                        print(f"[r{rnd}] {side} GLITCH: malformed/no offer")
                    continue

            if move.action == "OFFER":
                standing[side] = move.deal
                ev["deal"] = move.deal.as_dict()
            elif move.action == "ACCEPT":
                accepted = standing[opp]               # accept the OTHER side's offer
                ev["deal"] = accepted.as_dict() if accepted else None
                # Role/harness-specific rationality floor:
                #  - the BUYER is the fixed, rational benchmark opponent, and any
                #    VALIDATED (good-harness) agent must never close below its own
                #    BATNA -> floor = BATNA. Enforced here on the REAL standing
                #    offer (the executor's gate only sees the echoed deal).
                #  - a RAW/DEFAULT seller is floored only at 0 (no selling at a loss),
                #    so it can still close below BATNA: the citable, on-thesis
                #    execution-alignment error.
                floor = batna(side) if (side == "buyer" or cfg.validate_gate) else 0.0
                if accepted is not None and calc_utility(accepted, side) >= floor:
                    final_deal = accepted
                    outcome = "deal"
                    done = True
                elif accepted is not None:
                    invalid[side] += 1
                    ev["glitch"] = "rejected_irrational_accept"
                else:
                    invalid[side] += 1
                    ev["glitch"] = "accept_without_standing_offer"
            elif move.action == "WALK":
                outcome = "walk"
                done = True

            events.append(ev)
            if on_event: on_event(ev)
            history.append({"side": side, "line": _public_line(side, move),
                            "own_line": _own_line(move)})
            if verbose:
                tcount = len(move.tool_calls)
                print(f"[r{rnd}] {side:<6} {cfg.kind.value:<4} {move.action} "
                      f"{_render_offer(move.deal)}  tools={tcount} "
                      f"{'INVALID' if move.invalid else ''}")
            if done:
                break
        if done:
            break

    seller_harnessed = seller_cfg.kind == HarnessKind.GOOD
    score = score_outcome(final_deal, seller_is_harnessed=seller_harnessed)
    return MatchResult(
        final_deal=final_deal, score=score, events=events, rounds=rounds_played,
        total_cost_usd=round(total_cost, 6), invalid_offers=invalid, outcome=outcome,
    )


if __name__ == "__main__":
    # Quick single-match smoke test: small+GOOD seller vs large+RAW buyer.
    from bazaar80.harness import good_harness, raw_harness

    print("Running one match: seller=GOOD(small) vs buyer=RAW(large) ...\n")
    t0 = time.time()
    result = negotiate(
        good_harness("seller"),
        raw_harness("buyer"),
        max_rounds=5,
        verbose=True,
    )
    dt = time.time() - t0
    print("\n--- RESULT ---")
    print(f"outcome: {result.outcome}  rounds: {result.rounds}  "
          f"invalid: {result.invalid_offers}  cost: ${result.total_cost_usd:.4f}  "
          f"({dt:.1f}s)")
    print(f"final deal: {result.final_deal.as_dict() if result.final_deal else None}")
    s = result.score
    print(f"seller_surplus={s['seller_surplus']}  buyer_surplus={s['buyer_surplus']}  "
          f"seller_claim={s['seller_claim_pct']}%  in_zopa={s['in_zopa']}  "
          f"surplus_destroyed={s['surplus_destroyed']}")
