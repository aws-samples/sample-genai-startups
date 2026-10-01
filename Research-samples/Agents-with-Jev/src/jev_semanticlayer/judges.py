from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Callable

from jev_semanticlayer.config import Settings
from jev_semanticlayer.cost import calculate_usage
from jev_semanticlayer.frontier import FrontierResult, StrandsFrontierRunner
from jev_semanticlayer.jev import JevClient, JevJudgment
from jev_semanticlayer.schema import (
    AssessmentRun,
    EvidenceRecord,
    FrontierExtraction,
    IncidentStatus,
    RootCauseStatus,
    SemanticAssessment,
    UpdateType,
)


EXTRACTION_PROMPT = """
You are the grounding stage of an incident semantic compiler. Extract explicit
entities and claims from the supplied evidence. Do not decide incident status,
root-cause status, hypothesis support, supersession, or review requirements.
Preserve uncertainty in the concise summary and candidate hypothesis.
""".strip()


EXPLICIT_RESOLUTION = re.compile(
    r"\bincident (?:is|has been) resolved\b",
    flags=re.IGNORECASE,
)


def apply_semantic_rules(
    evidence: EvidenceRecord,
    jev: JevJudgment,
) -> JevJudgment:
    if not EXPLICIT_RESOLUTION.search(evidence.text):
        return jev

    root_cause_status = jev.root_cause_status
    if evidence.current_state.get("root_cause_status") == "confirmed":
        root_cause_status = RootCauseStatus.CONFIRMED

    diagnostics = dict(jev.diagnostics)
    diagnostics["semantic_rules"] = ["explicit_incident_resolution"]
    return replace(
        jev,
        update_type=UpdateType.RESOLUTION,
        incident_status=IncidentStatus.RESOLVED,
        root_cause_status=root_cause_status,
        supersedes_previous=True,
        needs_review=False,
        diagnostics=diagnostics,
    )


@dataclass(frozen=True)
class JudgeResult:
    assessment: SemanticAssessment
    frontier: FrontierResult
    jev: JevJudgment | None = None


class SemanticJudge(ABC):
    mode: str

    @abstractmethod
    def assess(self, evidence: EvidenceRecord, repetition: int) -> AssessmentRun:
        raise NotImplementedError


class HybridJudge(SemanticJudge):
    mode = "hybrid"

    def __init__(
        self,
        settings: Settings,
        frontier: StrandsFrontierRunner | None = None,
        jev_factory: Callable[[], JevClient] | None = None,
    ) -> None:
        self.settings = settings
        self.frontier = frontier or StrandsFrontierRunner(settings)
        self.jev_factory = jev_factory or (lambda: JevClient(settings))

    def assess(self, evidence: EvidenceRecord, repetition: int) -> AssessmentRun:
        extraction_result = self.frontier.run(
            output_model=FrontierExtraction,
            system_prompt=EXTRACTION_PROMPT,
            payload=evidence.model_dump(exclude={"current_state"}),
        )
        extraction = FrontierExtraction.model_validate(extraction_result.output)
        jev = self.jev_factory().judge(
            {
                "evidence": evidence.model_dump(),
                "frontier_extraction": extraction.model_dump(),
            }
        )
        jev = apply_semantic_rules(evidence, jev)
        assessment = SemanticAssessment(
            affected_service=extraction.affected_service,
            related_deployment=extraction.related_deployment,
            concise_summary=extraction.concise_summary,
            candidate_hypothesis=extraction.candidate_hypothesis,
            root_cause_claim=extraction.explicit_root_cause_claim,
            update_type=jev.update_type,
            incident_status=jev.incident_status,
            hypothesis_relation=jev.hypothesis_relation,
            root_cause_status=jev.root_cause_status,
            supersedes_previous=jev.supersedes_previous,
            confidence=jev.confidence,
            needs_review=jev.needs_review,
        )
        usage = calculate_usage(
            self.settings,
            frontier_input_tokens=extraction_result.input_tokens,
            frontier_output_tokens=extraction_result.output_tokens,
            jev_input_tokens=jev.input_tokens,
            jev_output_tokens=jev.output_tokens,
        )
        return AssessmentRun(
            mode=self.mode,
            case_id=evidence.case_id,
            repetition=repetition,
            assessment=assessment,
            usage=usage,
            latency_ms=extraction_result.latency_ms + jev.latency_ms,
            diagnostics={
                "frontier_extraction": extraction.model_dump(),
                "jev": jev.diagnostics,
            },
        )
