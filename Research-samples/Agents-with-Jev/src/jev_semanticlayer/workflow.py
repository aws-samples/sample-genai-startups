from __future__ import annotations

from jev_semanticlayer.judges import SemanticJudge
from jev_semanticlayer.resolver import IncidentResolver
from jev_semanticlayer.schema import (
    EvidenceRecord,
    IngestionResult,
    StoredClaim,
)
from jev_semanticlayer.store import StateStore


class SemanticIngestionWorkflow:
    def __init__(
        self,
        store: StateStore,
        judge: SemanticJudge,
        resolver: IncidentResolver | None = None,
    ) -> None:
        self.store = store
        self.judge = judge
        self.resolver = resolver or IncidentResolver()

    def process(self, evidence: EvidenceRecord) -> IngestionResult:
        claim_id = f"claim:{evidence.case_id}"
        existing = self.store.get_claim(evidence.service, claim_id)
        if existing:
            return IngestionResult(
                evidence_id=evidence.case_id,
                claim_id=claim_id,
                skipped=True,
                assessment=existing.assessment,
                state=self.store.get_current_state(evidence.service),
            )

        current = self.store.get_current_state(evidence.service)
        contextual_evidence = evidence.model_copy(
            update={"current_state": current.model_dump(mode="json")}
        )
        run = self.judge.assess(contextual_evidence, repetition=1)
        resolution = self.resolver.resolve(
            current,
            contextual_evidence,
            run.assessment,
            claim_id,
        )

        self.store.put_evidence(evidence)
        if resolution.superseded_claim_id:
            self.store.mark_claim_superseded(
                evidence.service,
                resolution.superseded_claim_id,
            )
        self.store.put_claim(
            StoredClaim(
                claim_id=claim_id,
                evidence_id=evidence.case_id,
                service=evidence.service,
                occurred_at=evidence.occurred_at,
                assessment=run.assessment,
                resolution=resolution.resolution,
                applied_to_state=resolution.applied,
                diagnostics=run.diagnostics,
            )
        )
        self.store.save_current_state(resolution.state)

        return IngestionResult(
            evidence_id=evidence.case_id,
            claim_id=claim_id,
            assessment=run.assessment,
            state=resolution.state,
        )
