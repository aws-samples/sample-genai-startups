from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from typesafe_sdk import Choice, Noul, TypeSafeClient

from jev_semanticlayer.config import Settings
from jev_semanticlayer.schema import (
    HypothesisRelation,
    IncidentStatus,
    RootCauseStatus,
    UpdateType,
)


@dataclass(frozen=True)
class JevJudgment:
    update_type: UpdateType
    incident_status: IncidentStatus
    hypothesis_relation: HypothesisRelation
    root_cause_status: RootCauseStatus
    supersedes_previous: bool
    confidence: float
    needs_review: bool
    input_tokens: int
    output_tokens: int
    latency_ms: float
    diagnostics: dict[str, Any]


class JevClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.typesafe_api_key:
            raise ValueError("TYPESAFE_API_KEY is required for hybrid mode")
        self.settings = settings

    def judge(self, state: dict[str, Any]) -> JevJudgment:
        questions = {
            "update_type": Choice(
                instructions=(
                    "Classify what the new evidence contributes to the incident."
                ),
                criteria={
                    "observation": "A symptom or measurement without a causal claim.",
                    "hypothesis": "A possible cause that remains unconfirmed.",
                    "confirmed_cause": "Evidence explicitly establishes or rejects a root cause.",
                    "mitigation": "An action intended to reduce impact.",
                    "resolution": "Evidence says the incident has ended or recovered.",
                },
            ),
            "incident_status": Choice(
                instructions=(
                    "Infer the resulting incident status after applying the new evidence "
                    "to the supplied current state. Preserve the current status unless "
                    "the evidence supports a transition."
                ),
                criteria={
                    "open": "The incident exists but active investigation is not established.",
                    "investigating": (
                        "A causal hypothesis exists, evidence is being evaluated, "
                        "or the cause or scope is under investigation."
                    ),
                    "mitigating": "A mitigation is being applied or monitored.",
                    "resolved": "The incident is explicitly resolved with recovery evidence.",
                },
            ),
            "hypothesis_relation": Choice(
                instructions=(
                    "How does the new evidence relate to the current hypothesis?"
                ),
                criteria={
                    "supports": "The evidence raises confidence in the hypothesis.",
                    "contradicts": "The evidence lowers confidence or rules it out.",
                    "unrelated": "The evidence concerns another cause or issue.",
                    "insufficient": "There is not enough information to judge the hypothesis.",
                },
            ),
            "root_cause_status": Choice(
                instructions=(
                    "Infer the resulting root-cause status after applying the new "
                    "evidence to the supplied current state. Preserve an already "
                    "confirmed cause unless the evidence revises or rejects it."
                ),
                criteria={
                    "unknown": "No usable causal hypothesis is established.",
                    "candidate": "A causal explanation is plausible but unconfirmed.",
                    "confirmed": "The evidence explicitly confirms a causal explanation.",
                    "rejected": "The evidence explicitly rules out the current hypothesis.",
                },
            ),
            "supersedes_previous": Noul(
                instructions=(
                    "Does applying this evidence replace, revise, reject, or close a "
                    "previously active incident status or root-cause claim?"
                ),
                criteria={
                    "true": (
                        "The evidence changes an existing status or claim, including "
                        "confirmation, rejection, revision, or resolution."
                    ),
                    "false": (
                        "The evidence adds detail while leaving the existing state intact."
                    ),
                },
            ),
        }

        started = perf_counter()
        with TypeSafeClient(
            api_key=self.settings.typesafe_api_key,
            model=self.settings.jev_model,
        ) as client:
            response = client.system_one(state=state, questions=questions)
        elapsed_ms = (perf_counter() - started) * 1000

        choices = response.choices
        supersedes_probability = response.nouls["supersedes_previous"].noul
        choice_confidences = [
            choices["update_type"].confidence,
            choices["incident_status"].confidence,
            choices["hypothesis_relation"].confidence,
            choices["root_cause_status"].confidence,
        ]
        confidence_values = choice_confidences + [
            abs(supersedes_probability - 0.5) * 2
        ]
        confidence = sum(confidence_values) / len(confidence_values)
        update_type = UpdateType(choices["update_type"].choice)
        incident_status = IncidentStatus(choices["incident_status"].choice)
        root_cause_status = RootCauseStatus(
            choices["root_cause_status"].choice
        )
        coherent_explicit_transition = (
            update_type is UpdateType.RESOLUTION
            and incident_status is IncidentStatus.RESOLVED
            and supersedes_probability >= 0.5
        ) or (
            update_type is UpdateType.CONFIRMED_CAUSE
            and root_cause_status is RootCauseStatus.CONFIRMED
        )
        needs_review = (
            confidence < self.settings.review_confidence_threshold
            and not coherent_explicit_transition
        )

        return JevJudgment(
            update_type=update_type,
            incident_status=incident_status,
            hypothesis_relation=HypothesisRelation(
                choices["hypothesis_relation"].choice
            ),
            root_cause_status=root_cause_status,
            supersedes_previous=supersedes_probability >= 0.5,
            confidence=confidence,
            needs_review=needs_review,
            input_tokens=response.usage.input_tokens or 0,
            output_tokens=response.usage.output_tokens or 0,
            latency_ms=elapsed_ms,
            diagnostics={
                "model": response.model,
                "answers": {
                    name: answer.model_dump()
                    for name, answer in response.answers.items()
                },
            },
        )
