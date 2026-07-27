"""Bazaar-80 negotiation game (ZERO-SUM / distributive edition).

The offline, deterministic core of the demo. A fixed wholesale bundle is sold;
two issues (price, payment terms) are BOTH pure transfers -- every dollar one
side gains, the other loses. So the joint surplus (the "pie") is CONSTANT across
every possible deal. There is no win-win to discover: the entire negotiation is
about the SPLIT.

Two issues, not three, on purpose: price is the headline number everyone tracks,
and payment_terms is a structurally distinct "side" lever (a pure transfer with
non-round costs the calculator tool protects against). A third issue (delivery)
was dropped because it was mechanically identical to payment_terms -- a second
copy of the same lever taught the audience nothing while doubling what they had
to read on screen.

Why zero-sum (the harder case, deliberately):
  - It doesn't converge easily. With a narrow zone of possible agreement (ZOPA)
    and real outside options (BATNAs), naive agents anchor, fail to find the
    overlapping window in limited rounds, and WALK -- destroying the whole pie.
  - It removes the "look good by growing the pie and conceding" escape hatch.
    A harness can only win by CLAIMING (precise BATNA math, holding firm,
    inferring the opponent's reservation) and CLOSING (agreeing when a deal is
    there to be made). That is exactly what scaffolding is supposed to provide.

Headline outcome measures (no efficiency story in zero-sum -- every closed deal
is Pareto-optimal):
  - seller_surplus and seller_claim_pct (share of the divisible surplus the
    seller captured: 50% = even split, 100% = seller took everything),
  - deal rate (did they converge at all?),
  - surplus_destroyed on a no-deal (the cost of failing to agree).

Everything is computable with no model and no AWS credentials.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Deal space (discrete, fully enumerable): 5 x 3 = 15 deals
# --------------------------------------------------------------------------- #

PRICES: Tuple[float, ...] = (6.0, 7.0, 8.0, 9.0, 10.0)          # $ per unit
PAYMENT_TERMS: Tuple[str, ...] = ("prepaid", "net30", "net60")

# Fixed bundle size (NOT negotiable). Kept as a constant so price x quantity is
# still fiddly arithmetic the calculator tool protects against, without quantity
# changing the size of the pie (which would reintroduce an integrative issue).
QUANTITY = 300

# --------------------------------------------------------------------------- #
# Utility-table constants (non-round on purpose, to punish mental arithmetic)
# --------------------------------------------------------------------------- #

SELLER_UNIT_COST = 5.20            # seller's cost basis per widget
BUYER_UNIT_VALUE = 9.50           # buyer's value per widget

SELLER_COST = SELLER_UNIT_COST * QUANTITY     # 1560.0
BUYER_VALUE = BUYER_UNIT_VALUE * QUANTITY     # 2850.0

# Pure transfer: the amount each payment term moves FROM the seller TO the buyer
# (relative to the seller-favorable baseline of prepaid). Because the seller's
# loss equals the buyer's gain exactly, this changes only the split.
PAYMENT_TRANSFER: Dict[str, float] = {"prepaid": 0.0, "net30": 150.0, "net60": 300.0}

# BATNA / walkaway: each side's outside option. With both at 400 and a constant
# pie of (BUYER_VALUE - SELLER_COST) = 1290, the divisible surplus is 1290 - 800
# = 490, and the ZOPA is narrow (acceptable deals cluster at price 7-9 with the
# right term trades), so convergence takes real skill.
SELLER_BATNA = 400.0
BUYER_BATNA = 400.0

PIE = round(BUYER_VALUE - SELLER_COST, 2)                       # 1290.0 (constant)
DIVISIBLE_SURPLUS = round(PIE - SELLER_BATNA - BUYER_BATNA, 2)  # 490.0


def set_batnas(seller_batna: float, buyer_batna: float) -> None:
    """Override both BATNAs at runtime (scenarios use this to set ZOPA width).

    Rebinds module globals; all scoring/IR functions read them at call time, so
    the change takes effect immediately for subsequent matches.
    """
    global SELLER_BATNA, BUYER_BATNA, DIVISIBLE_SURPLUS
    SELLER_BATNA = float(seller_batna)
    BUYER_BATNA = float(buyer_batna)
    DIVISIBLE_SURPLUS = round(PIE - SELLER_BATNA - BUYER_BATNA, 2)


@dataclass(frozen=True)
class Deal:
    """A concrete, fully specified deal across both distributive issues."""

    unit_price: float
    payment_terms: str

    def is_valid(self) -> bool:
        return (
            self.unit_price in PRICES
            and self.payment_terms in PAYMENT_TERMS
        )

    def as_dict(self) -> Dict[str, object]:
        return {"unit_price": self.unit_price,
                "payment_terms": self.payment_terms}


# --------------------------------------------------------------------------- #
# Utility functions (constructed so seller + buyer == PIE for every deal)
# --------------------------------------------------------------------------- #

def _transfer(deal: Deal) -> float:
    return PAYMENT_TRANSFER[deal.payment_terms]


def seller_utility(deal: Deal) -> float:
    """Seller profit: revenue - cost - value transferred to the buyer."""
    return round(deal.unit_price * QUANTITY - SELLER_COST - _transfer(deal), 2)


def buyer_utility(deal: Deal) -> float:
    """Buyer surplus: value - price paid + value transferred from the seller."""
    return round(BUYER_VALUE - deal.unit_price * QUANTITY + _transfer(deal), 2)


def joint_surplus(deal: Deal) -> float:
    """Constant by construction (== PIE). Present for symmetry / sanity checks."""
    return round(seller_utility(deal) + buyer_utility(deal), 2)


def is_individually_rational(deal: Deal) -> bool:
    """True if the deal beats BOTH parties' walkaway (i.e., it is in the ZOPA)."""
    return seller_utility(deal) >= SELLER_BATNA and buyer_utility(deal) >= BUYER_BATNA


# --------------------------------------------------------------------------- #
# Deal-space enumeration and reference points
# --------------------------------------------------------------------------- #

def all_deals() -> List[Deal]:
    return [Deal(p, pt) for p, pt in itertools.product(PRICES, PAYMENT_TERMS)]


def bargaining_set() -> List[Deal]:
    """The ZOPA: deals that clear both BATNAs. These are the only agreeable deals."""
    return [d for d in all_deals() if is_individually_rational(d)]


def max_seller_surplus() -> float:
    """Best split the seller can get while keeping the buyer in the ZOPA."""
    bs = bargaining_set()
    return max((seller_utility(d) for d in bs), default=SELLER_BATNA)


def min_seller_surplus() -> float:
    """Worst in-ZOPA split for the seller (buyer claims the most)."""
    bs = bargaining_set()
    return min((seller_utility(d) for d in bs), default=SELLER_BATNA)


def nash_bargaining_deal() -> Deal:
    """The deal maximizing the Nash product of surpluses above each BATNA -- the
    'fair' even-split reference for the scoreboard."""
    candidates = bargaining_set() or all_deals()

    def nash_product(d: Deal) -> float:
        return (seller_utility(d) - SELLER_BATNA) * (buyer_utility(d) - BUYER_BATNA)

    return max(candidates, key=nash_product)


# --------------------------------------------------------------------------- #
# Outcome scoring (what the HUD / scoreboard / batch metrics consume)
# --------------------------------------------------------------------------- #

def _seller_claim_pct(seller_surplus: float) -> float:
    """Seller's share of the TOTAL pie (0..100%, fair split == 50%).

    Defined against the whole pie rather than the divisible surplus so it stays
    bounded and intuitive even when the opponent makes an execution-alignment
    error (accepting below its own BATNA): the seller simply captured a larger
    share of the fixed pie.
    """
    if PIE <= 0:
        return 0.0
    return round(100.0 * seller_surplus / PIE, 1)


def score_outcome(deal: Optional[Deal], *, seller_is_harnessed: bool) -> Dict[str, object]:
    """Score a negotiated outcome. `deal` is None for a no-deal (walk/timeout):
    both sides realize only their BATNA and the divisible surplus is destroyed."""
    if deal is None:
        return {
            "deal_reached": False,
            "deal": None,
            "valid": False,
            "seller_surplus": SELLER_BATNA,
            "buyer_surplus": BUYER_BATNA,
            "joint_surplus": SELLER_BATNA + BUYER_BATNA,
            "pie": PIE,
            "seller_claim_pct": 0.0,
            "surplus_destroyed": DIVISIBLE_SURPLUS,
            "individually_rational": True,       # both took their outside option
            "in_zopa": False,
            "seller_is_harnessed": seller_is_harnessed,
        }

    s = seller_utility(deal)
    b = buyer_utility(deal)
    return {
        "deal_reached": True,
        "deal": deal.as_dict(),
        "valid": deal.is_valid(),
        "seller_surplus": s,
        "buyer_surplus": b,
        "joint_surplus": joint_surplus(deal),
        "pie": PIE,
        "seller_claim_pct": _seller_claim_pct(s),
        "surplus_destroyed": 0.0,
        "individually_rational": is_individually_rational(deal),
        "in_zopa": is_individually_rational(deal),
        "seller_is_harnessed": seller_is_harnessed,
    }


# --------------------------------------------------------------------------- #
# Offline self-test (no AWS, no model) -- run: python game.py
# --------------------------------------------------------------------------- #

def _self_test() -> None:
    print("=" * 64)
    print("BAZAAR-80 game self-test (zero-sum / distributive)")
    print("=" * 64)

    deals = all_deals()
    print(f"deal space size: {len(deals)}  "
          f"({len(PRICES)} prices x {len(PAYMENT_TERMS)} terms)")
    print(f"PIE (constant) = {PIE}   divisible surplus = {DIVISIBLE_SURPLUS}   "
          f"BATNAs = {SELLER_BATNA}/{BUYER_BATNA}")

    # Zero-sum invariant: joint surplus is identical for every deal.
    joints = {joint_surplus(d) for d in deals}
    assert joints == {PIE}, joints
    print(f"OK: every one of {len(deals)} deals has identical joint surplus = {PIE} (zero-sum)")

    bs = bargaining_set()
    print(f"\nZOPA (agreeable deals clearing both BATNAs): {len(bs)} of {len(deals)}")
    for d in sorted(bs, key=seller_utility):
        print(f"  {d.as_dict()!s:<62} seller={seller_utility(d):>7.1f}  buyer={buyer_utility(d):>7.1f}")
    assert bs, "ZOPA must be non-empty or no deal is ever possible"

    print(f"\nseller claim range in ZOPA: {min_seller_surplus():.0f} .. {max_seller_surplus():.0f}  "
          f"(claim% {_seller_claim_pct(min_seller_surplus()):.0f}% .. "
          f"{_seller_claim_pct(max_seller_surplus()):.0f}%)")

    nash = nash_bargaining_deal()
    print(f"Nash (fair) split: {nash.as_dict()}  "
          f"seller={seller_utility(nash):.0f} ({_seller_claim_pct(seller_utility(nash)):.0f}%)  "
          f"buyer={buyer_utility(nash):.0f}")

    # Illustrate the harness gap in zero-sum terms: claiming + closing.
    print("\n--- harness gap illustration ---")
    seller_win = Deal(9.0, "net60")    # seller holds price high, trades the term
    buyer_win = Deal(7.0, "prepaid")   # buyer pinned price low
    for label, d in (("seller claims well", seller_win), ("seller caved", buyer_win)):
        if not is_individually_rational(d):
            print(f"  {label}: {d.as_dict()} NOT in ZOPA (would be walked)")
            continue
        sc = score_outcome(d, seller_is_harnessed=True)
        print(f"  {label}: {d.as_dict()}")
        print(f"      seller={sc['seller_surplus']:.0f} ({sc['seller_claim_pct']:.0f}% of divisible)  "
              f"buyer={sc['buyer_surplus']:.0f}")

    nod = score_outcome(None, seller_is_harnessed=False)
    print(f"\n  no-deal (walk): seller={nod['seller_surplus']:.0f} buyer={nod['buyer_surplus']:.0f}  "
          f"surplus_destroyed={nod['surplus_destroyed']:.0f}  (the cost of failing to converge)")

    print("\nAll self-test assertions passed.")


if __name__ == "__main__":
    _self_test()
