from __future__ import annotations

from dataclasses import dataclass

from jev_semanticlayer.schema import (
    EvidenceRecord,
    IncidentState,
    RootCauseStatus,
    SemanticAssessment,
)


@dataclass(frozen=True)
class Resolution:
    state: IncidentState
    resolution: str
    applied: bool
    superseded_claim_id: str | None = None


class IncidentResolver:
    def resolve(
        self,
        current: IncidentState,
        evidence: EvidenceRecord,
        assessment: SemanticAssessment,
        claim_id: str,
    ) -> Resolution:
        state = current.model_copy(deep=True)
        if evidence.case_id not in state.evidence_ids:
            state.evidence_ids.append(evidence.case_id)

        if assessment.needs_review:
            if claim_id not in state.pending_review_ids:
                state.pending_review_ids.append(claim_id)
            state.updated_at = evidence.occurred_at
            return Resolution(
                state=state,
                resolution="pending_review",
                applied=False,
            )

        superseded_claim_id = (
            state.active_claim_id
            if assessment.supersedes_previous
            else None
        )
        state.incident_status = assessment.incident_status
        state.related_deployment = (
            assessment.related_deployment or state.related_deployment
        )

        if assessment.root_cause_status is RootCauseStatus.CONFIRMED:
            state.root_cause_status = RootCauseStatus.CONFIRMED
            confirmed = (
                assessment.root_cause_claim
                or assessment.candidate_hypothesis
                or state.confirmed_root_cause
                or state.current_hypothesis
            )
            state.confirmed_root_cause = confirmed
            state.current_hypothesis = confirmed
        elif assessment.root_cause_status is RootCauseStatus.REJECTED:
            state.root_cause_status = RootCauseStatus.REJECTED
            state.current_hypothesis = None
        elif assessment.root_cause_status is RootCauseStatus.CANDIDATE:
            if state.root_cause_status is not RootCauseStatus.CONFIRMED:
                state.root_cause_status = RootCauseStatus.CANDIDATE
                state.current_hypothesis = (
                    assessment.candidate_hypothesis
                    or state.current_hypothesis
                )
        elif state.root_cause_status is not RootCauseStatus.CONFIRMED:
            state.root_cause_status = RootCauseStatus.UNKNOWN

        state.active_claim_id = claim_id
        state.updated_at = evidence.occurred_at
        return Resolution(
            state=state,
            resolution="active",
            applied=True,
            superseded_claim_id=superseded_claim_id,
        )

