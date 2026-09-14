from __future__ import annotations

import argparse
import asyncio
import json

from .fixtures import (
    REQUEST,
    FixtureResearcher,
    FixtureSemanticVerifier,
    Scenario,
)
from .loop import VerifiedResearchLoop


async def run(scenario: Scenario) -> dict:
    workflow = VerifiedResearchLoop(
        FixtureResearcher(scenario),
        FixtureSemanticVerifier(),
    )
    result = await workflow.run(REQUEST)
    return result.model_dump(mode="json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a controlled verified-goal research scenario."
    )
    parser.add_argument(
        "scenario",
        choices=[item.value for item in Scenario],
        nargs="?",
        default=Scenario.IMMEDIATE_ACCEPTANCE.value,
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(Scenario(args.scenario))), indent=2))


if __name__ == "__main__":
    main()
