"""Stage 2: gate model changes against real outputs from the same ticket agent."""

import os
import sys

from reliable_inference import EvalCase, EvalReport, run_eval_suite


TICKET_SUITE = (
    EvalCase(
        name="shipped order",
        ticket="Where is order #10042?",
        order_context="Order #10042 shipped on 4 August. Tracking ID ZX-1942.",
        required_terms=("#10042", "shipped"),
        allowed_order_ids=frozenset({"10042"}),
    ),
    EvalCase(
        name="address change",
        ticket="Can I change the address for order #10043?",
        order_context="Order #10043 is processing. Its shipping address can still be changed.",
        required_terms=("#10043", "address"),
        allowed_order_ids=frozenset({"10043"}),
    ),
    EvalCase(
        name="unknown order",
        ticket="Where is order #99999?",
        order_context="No matching order was found. Ask the customer to verify the order ID.",
        required_terms=("#99999", "verify"),
        allowed_order_ids=frozenset({"99999"}),
    ),
)


def describe(report: EvalReport) -> None:
    print(
        f"{report.model_id} pass_rate={report.pass_rate:.0%} "
        f"output_tokens={report.output_tokens} violations={report.violations()}"
    )
    for outcome in report.outcomes:
        print(f"  {outcome.case_name}: {outcome.violations or 'PASS'}")


def main() -> int:
    baseline_id = os.getenv(
        "BEDROCK_MODEL_ID",
        "global.amazon.nova-2-lite-v1:0",
    )
    candidate_id = os.getenv("BEDROCK_CANDIDATE_MODEL_ID", "us.amazon.nova-micro-v1:0")

    baseline = run_eval_suite(baseline_id, TICKET_SUITE)
    candidate = run_eval_suite(candidate_id, TICKET_SUITE)
    describe(baseline)
    describe(candidate)

    if candidate.pass_rate < baseline.pass_rate or candidate.pass_rate < 1:
        print("release blocked: candidate did not preserve the required behavior")
        return 1
    print("release gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
