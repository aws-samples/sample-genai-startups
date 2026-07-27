"""Bazaar-80 scenarios: a small, curated set the demo user chooses from.

Rather than an open prompt, the demo presents 3-4 fixed scenarios. Each is the
same zero-sum widget negotiation but tuned (mainly via the BATNAs = ZOPA width,
the opponent's style, and the round budget) to stress ONE harness skill, so the
harness-on vs harness-off contrast lands a single clear point each time.

These are data only. The runner applies a scenario by overriding the game's
BATNAs and the buyer's style, then runs the same negotiate loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str                 # arcade-style title for the SELECT screen
    tagline: str              # one line shown under the title
    teaches: str              # the harness skill this isolates
    seller_batna: float       # overrides game.SELLER_BATNA (sets ZOPA width)
    buyer_batna: float        # overrides game.BUYER_BATNA
    max_rounds: int
    buyer_style: str          # prompt modifier appended to the buyer persona
    # What the audience should watch the harness do vs the raw/bad config:
    harness_win: str
    raw_failure: str


# --------------------------------------------------------------------------- #
# The curated set
# --------------------------------------------------------------------------- #

SCENARIOS: List[Scenario] = [
    Scenario(
        id="tight_window",
        name="NARROW MARGIN",
        tagline="There is very little room for a deal here. Can the trader find the "
                "small overlap and agree, or walk away with nothing?",
        teaches="CLOSING: finding the overlap and agreeing instead of walking away from money",
        # Pie is 1290; with both BATNAs at 450 the divisible surplus is 390 and
        # the ZOPA is narrow but sound (seller surplus 450..840) -- enough room
        # that closing vs walking, not validator boundary effects, is the story.
        seller_batna=450.0,
        buyer_batna=450.0,
        max_rounds=8,
        buyer_style=("You are firm and a little impatient. You will not chase the deal; "
                     "if terms drift away from your walkaway you are ready to walk."),
        harness_win=("Calculator pins the exact walkaway and validator stops a premature "
                     "WALK, so the harness finds the sliver of a deal and closes it."),
        raw_failure=("Without precise BATNA math the raw/bad config can't tell a barely-"
                     "good deal from a bad one and walks away -- destroying the whole pie."),
    ),
    Scenario(
        id="anchor_war",
        name="AGGRESSIVE OPENER",
        tagline="The other side opens with a very low offer. Does the trader hold its "
                "ground and negotiate back, or give away the profit?",
        teaches="CLAIMING: holding firm against an aggressive anchor instead of caving",
        # Wide ZOPA (low BATNAs => big divisible surplus) so the whole story is
        # the split. An aggressive opponent punishes timidity.
        seller_batna=300.0,
        buyer_batna=300.0,
        max_rounds=7,
        buyer_style=("You are an aggressive anchorer: open with an extreme lowball, concede "
                     "slowly and grudgingly, and push hard on every counter."),
        harness_win=("Scratchpad infers the buyer's real walkaway and the validator refuses "
                     "self-harming concessions, so the harness anchors back and claims the "
                     "bulk of the surplus."),
        raw_failure=("The raw config anchors weakly and the guardrail config concedes to "
                     "keep the peace -- both hand the buyer most of the pie."),
    ),
    Scenario(
        id="fine_print",
        name="HIDDEN VALUE",
        tagline="The price is not the whole story -- real value is hidden in the "
                "payment terms. Do the math right to come out ahead.",
        teaches="CALCULATION: trading the side issue correctly instead of fumbling the math",
        # Moderate ZOPA; the win comes from trading payment_terms (a pure transfer
        # with non-round costs) to hold price -- easy to miscompute.
        seller_batna=400.0,
        buyer_batna=400.0,
        max_rounds=7,
        buyer_style=("You bargain reasonably but will exploit any seller who miscalculates "
                     "the cost of a concession or makes a malformed offer."),
        harness_win=("Calculator gets every transfer right and the validator blocks illegal "
                     "or self-harming offers, so the harness trades terms to hold price."),
        raw_failure=("The raw config slips on the non-round transfer math and the guardrail "
                     "config emits malformed offers, leaking surplus and wasting turns."),
    ),
    Scenario(
        id="marathon",
        name="THE LONG HAUL",
        tagline="A marathon haggle. Keep track of every offer on the table, or get "
                "lost in the endless back-and-forth.",
        teaches="MEMORY: tracking the negotiation state over many rounds",
        # Long horizon exposes context handling: weak context management makes an
        # agent forget prior offers and contradict itself.
        seller_batna=400.0,
        buyer_batna=400.0,
        max_rounds=12,
        buyer_style=("You negotiate patiently over many rounds and will call out the seller "
                     "if they contradict or repeat an offer already rejected."),
        harness_win=("Summarized rolling memory keeps the harness consistent across rounds, "
                     "so it converges on a strong split."),
        raw_failure=("A weak context policy forgets earlier offers, contradicts "
                     "itself, and loops until the round budget runs out."),
    ),
]

SCENARIOS_BY_ID: Dict[str, Scenario] = {s.id: s for s in SCENARIOS}

# The default 3-scenario demo set (Marathon is the optional 4th).
DEFAULT_SET: List[str] = ["tight_window", "anchor_war", "fine_print"]


def get_scenario(scenario_id: str) -> Scenario:
    if scenario_id not in SCENARIOS_BY_ID:
        raise KeyError(f"unknown scenario {scenario_id!r}; "
                       f"choices: {list(SCENARIOS_BY_ID)}")
    return SCENARIOS_BY_ID[scenario_id]


if __name__ == "__main__":
    for s in SCENARIOS:
        flag = "" if s.id in DEFAULT_SET else "  (optional 4th)"
        print(f"[{s.id}] {s.name}{flag}")
        print(f"    {s.tagline}")
        print(f"    teaches : {s.teaches}")
        print(f"    ZOPA    : seller_batna={s.seller_batna:g} buyer_batna={s.buyer_batna:g} "
              f"rounds={s.max_rounds}")
        print(f"    win     : {s.harness_win}")
        print(f"    failure : {s.raw_failure}\n")
