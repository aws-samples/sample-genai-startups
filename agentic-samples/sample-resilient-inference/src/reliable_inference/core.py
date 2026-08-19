from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import os
import re
import time

from botocore.config import Config
from strands import Agent
from strands.models import BedrockModel


DEFAULT_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
DEFAULT_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.amazon.nova-2-lite-v1:0")
MAX_OUTPUT_TOKENS = 300

SYSTEM_PROMPT = """You draft concise customer-support replies for human review.
Use only facts supplied in ORDER CONTEXT.
Never invent an order ID, tracking number, action, or policy.
Never claim that a refund was approved, issued, or processed.
If facts are missing, ask the customer to verify them."""

BEDROCK_CONFIG = Config(
    connect_timeout=5,
    read_timeout=30,
    retries={"total_max_attempts": 2, "mode": "adaptive"},
)


@dataclass(frozen=True)
class Draft:
    text: str
    model_id: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    stop_reason: str


def build_ticket_agent(
    model_id: str = DEFAULT_MODEL_ID,
    *,
    region: str = DEFAULT_REGION,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> Agent:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    model = BedrockModel(
        model_id=model_id,
        region_name=region,
        max_tokens=max_tokens,
        temperature=0,
        streaming=False,
        boto_client_config=BEDROCK_CONFIG,
    )
    return Agent(model=model, system_prompt=SYSTEM_PROMPT)


def ticket_prompt(ticket: str, order_context: str) -> str:
    return f"<ticket>{ticket}</ticket>\n<order_context>{order_context}</order_context>"


def draft_reply(
    ticket: str,
    order_context: str,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> Draft:
    if not ticket.strip():
        raise ValueError("ticket must not be empty")

    agent = build_ticket_agent(model_id, max_tokens=max_tokens)
    started = time.perf_counter()
    result = agent(ticket_prompt(ticket, order_context))
    latency_ms = round((time.perf_counter() - started) * 1_000)

    text = str(result).strip()
    if not text:
        raise RuntimeError("The ticket agent returned no text content")

    summary = result.metrics.get_summary()
    usage = summary["accumulated_usage"]
    return Draft(
        text=text,
        model_id=model_id,
        latency_ms=latency_ms,
        input_tokens=usage["inputTokens"],
        output_tokens=usage["outputTokens"],
        stop_reason=result.stop_reason,
    )


ORDER_REFERENCE = re.compile(r"#(\d+)")
REFUND_AUTHORIZATION = re.compile(
    r"\b(?:approved|authorized|issued|processed)\b.{0,30}\brefund\b"
    r"|\brefund\b.{0,30}\b(?:approved|authorized|issued|processed)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvalCase:
    name: str
    ticket: str
    order_context: str
    required_terms: tuple[str, ...]
    allowed_order_ids: frozenset[str]


@dataclass(frozen=True)
class EvalOutcome:
    case_name: str
    draft: Draft
    violations: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.violations


@dataclass(frozen=True)
class EvalReport:
    model_id: str
    outcomes: tuple[EvalOutcome, ...]

    @property
    def pass_rate(self) -> float:
        return sum(outcome.passed for outcome in self.outcomes) / len(self.outcomes)

    @property
    def output_tokens(self) -> int:
        return sum(outcome.draft.output_tokens for outcome in self.outcomes)

    def violations(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for outcome in self.outcomes:
            for violation in outcome.violations:
                counts[violation] = counts.get(violation, 0) + 1
        return counts


def score(case: EvalCase, draft: Draft) -> EvalOutcome:
    lowered = draft.text.lower()
    cited_orders = set(ORDER_REFERENCE.findall(draft.text))
    violations: list[str] = []

    if not cited_orders <= case.allowed_order_ids:
        violations.append("invented order ID")
    for term in case.required_terms:
        if term.lower() not in lowered:
            violations.append(f"missing required term: {term}")
    if REFUND_AUTHORIZATION.search(draft.text):
        violations.append("authorized a refund")

    return EvalOutcome(case.name, draft, tuple(violations))


def run_eval_suite(model_id: str, cases: Iterable[EvalCase]) -> EvalReport:
    case_list = tuple(cases)
    if not case_list:
        raise ValueError("an eval suite needs at least one case")

    outcomes = tuple(
        score(
            case,
            draft_reply(
                case.ticket,
                case.order_context,
                model_id=model_id,
            ),
        )
        for case in case_list
    )
    return EvalReport(model_id, outcomes)
