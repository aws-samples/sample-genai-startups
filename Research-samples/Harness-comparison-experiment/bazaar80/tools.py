"""Deterministic harness tools: calculator, offer validator, BATNA lookup.

These are plain Python so they're reproducible and free. They are exposed to the
model as Strands @tool functions (see harness.py `_strands_tool`); the DEFAULT
and GOOD tiers both get them, while RAW does not. The deterministic
calculator/validator behind the tools is also what GOOD's code-based commit gate
calls to bounce an illegal or self-harming offer BEFORE it is sent -- a gate the
other tiers lack. Those two asymmetries (who has tools, who has the gate) are the
experiment.

Also holds the robust JSON-move parser the negotiation loop uses for every
agent, so a malformed model output is detected (not silently mis-read).
"""

from __future__ import annotations

import json
import re
from typing import Dict, Optional, Tuple

from bazaar80 import game
from bazaar80.game import (
    PAYMENT_TERMS,
    PRICES,
    Deal,
    buyer_utility,
    seller_utility,
)

Role = str  # "seller" | "buyer"


# --------------------------------------------------------------------------- #
# Calculator tool: exact utility for a candidate deal (kills arithmetic slips)
# --------------------------------------------------------------------------- #

def calc_utility(deal: Deal, role: Role) -> float:
    """Exact surplus for `role` under `deal`. The harness uses this so the model
    never has to eyeball price x quantity."""
    return seller_utility(deal) if role == "seller" else buyer_utility(deal)


def batna(role: Role) -> float:
    """The walkaway value for `role`. Offers below this are self-harming.
    Reads game's BATNAs dynamically so scenario overrides take effect."""
    return game.SELLER_BATNA if role == "seller" else game.BUYER_BATNA


# --------------------------------------------------------------------------- #
# Offer validator: legality + individual rationality + format
# --------------------------------------------------------------------------- #

def validate_offer(deal: Optional[Deal], role: Role) -> Tuple[bool, str]:
    """Return (ok, reason).

    Rejects two failure classes the demo cares about:
      1. malformed / out-of-space deals (illegal issue values),
      2. self-harming deals (below this role's BATNA).
    Only the GOOD harness's commit gate uses this to bounce a bad candidate
    BEFORE it's sent; RAW and DEFAULT have no such gate.
    """
    if deal is None:
        return False, "no parseable deal"
    if deal.unit_price not in PRICES:
        return False, f"illegal unit_price {deal.unit_price!r} (allowed {PRICES})"
    if deal.payment_terms not in PAYMENT_TERMS:
        return False, f"illegal payment_terms {deal.payment_terms!r} (allowed {PAYMENT_TERMS})"
    u = calc_utility(deal, role)
    if u < batna(role):
        return False, f"self-harming: {role} utility {u:.2f} < BATNA {batna(role):.2f}"
    return True, "ok"


# --------------------------------------------------------------------------- #
# Move parsing (shared by every harness so malformed output is caught)
# --------------------------------------------------------------------------- #

VALID_ACTIONS = {"OFFER", "ACCEPT", "WALK"}


def _coerce_number(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_move(text: str) -> Tuple[Optional[str], Optional[Deal], str, bool]:
    """Parse a model turn into (action, deal, message, parse_ok).

    `parse_ok` is False when the output didn't yield a usable action -- that is
    an invalid/format failure, counted against the agent. We extract the first
    balanced {...} block to tolerate stray prose around the JSON.
    """
    if not text:
        return None, None, "", False

    blob = _extract_json_block(text)
    if blob is None:
        return None, None, text.strip()[:160], False
    try:
        obj = json.loads(blob)
    except json.JSONDecodeError:
        return None, None, text.strip()[:160], False

    action = str(obj.get("action", "")).upper().strip()
    if action not in VALID_ACTIONS:
        return None, None, str(obj.get("message", ""))[:160], False

    message = str(obj.get("message", ""))[:200]
    deal = None
    raw_deal = obj.get("deal")
    if isinstance(raw_deal, dict):
        price = _coerce_number(raw_deal.get("unit_price"))
        terms = raw_deal.get("payment_terms")
        if price is not None and isinstance(terms, str):
            deal = Deal(price, terms.strip().lower())

    # WALK doesn't need a deal; OFFER/ACCEPT do.
    if action in {"OFFER", "ACCEPT"} and deal is None:
        return action, None, message, False
    return action, deal, message, True


def _extract_json_block(text: str) -> Optional[str]:
    """Return the first balanced top-level {...} substring, else None."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def snap_to_legal(deal: Deal) -> Deal:
    """Snap an out-of-space deal to the nearest legal values.

    Used to KEEP THE NEGOTIATION ALIVE when an un-gated agent (RAW/DEFAULT)
    fumbles the format, while the fumble is still recorded as an invalid-offer
    event. The GOOD harness never needs this because its validator gates first.
    """
    price = min(PRICES, key=lambda p: abs(p - deal.unit_price))
    terms = deal.payment_terms if deal.payment_terms in PAYMENT_TERMS else "prepaid"
    return Deal(price, terms)
