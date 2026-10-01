from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UpdateType(StrEnum):
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    CONFIRMED_CAUSE = "confirmed_cause"
    MITIGATION = "mitigation"
    RESOLUTION = "resolution"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"


class HypothesisRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    UNRELATED = "unrelated"
    INSUFFICIENT = "insufficient"


class RootCauseStatus(StrEnum):
    UNKNOWN = "unknown"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EvidenceRecord(StrictModel):
    case_id: str
    service: str
    source: str
    occurred_at: str
    text: str
    current_state: dict[str, Any] = Field(default_factory=dict)


class FrontierExtraction(StrictModel):
    affected_service: str
    related_deployment: str | None
    concise_summary: str
    candidate_hypothesis: str | None
    explicit_root_cause_claim: str | None


class SemanticAssessment(StrictModel):
    affected_service: str
    related_deployment: str | None
    concise_summary: str
    candidate_hypothesis: str | None
    root_cause_claim: str | None = None
    update_type: UpdateType
    incident_status: IncidentStatus
    hypothesis_relation: HypothesisRelation
    root_cause_status: RootCauseStatus
    supersedes_previous: bool
    confidence: float = Field(ge=0, le=1)
    needs_review: bool

    def consistency_signature(self) -> tuple[str, ...]:
        return (
            self.affected_service,
            self.related_deployment or "",
            self.update_type.value,
            self.incident_status.value,
            self.hypothesis_relation.value,
            self.root_cause_status.value,
            str(self.supersedes_previous),
            str(self.needs_review),
        )


class Usage(StrictModel):
    frontier_input_tokens: int = 0
    frontier_output_tokens: int = 0
    jev_input_tokens: int = 0
    jev_output_tokens: int = 0
    frontier_cost_usd: float = 0
    jev_cost_usd: float = 0
    total_cost_usd: float = 0


class AssessmentRun(StrictModel):
    mode: str
    case_id: str
    repetition: int
    assessment: SemanticAssessment
    usage: Usage
    latency_ms: float
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class IncidentState(StrictModel):
    service: str
    incident_id: str
    incident_status: IncidentStatus = IncidentStatus.OPEN
    root_cause_status: RootCauseStatus = RootCauseStatus.UNKNOWN
    current_hypothesis: str | None = None
    confirmed_root_cause: str | None = None
    related_deployment: str | None = None
    active_claim_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    pending_review_ids: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class StoredClaim(StrictModel):
    claim_id: str
    evidence_id: str
    service: str
    occurred_at: str
    assessment: SemanticAssessment
    resolution: str
    applied_to_state: bool
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class IngestionResult(StrictModel):
    evidence_id: str
    claim_id: str
    skipped: bool = False
    assessment: SemanticAssessment | None = None
    state: IncidentState
