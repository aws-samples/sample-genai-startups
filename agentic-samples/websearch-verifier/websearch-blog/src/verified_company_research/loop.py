from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol
from urllib.parse import urlparse

from pydantic import ValidationError

from .contracts import (
    AgentSubmission,
    ClaimRepairProposal,
    CompanyResearchPackage,
    FieldName,
    FieldSubmission,
    FieldVerdict,
    GateIssue,
    REQUIRED_FIELDS,
    RecoveryAction,
    ResearchRequest,
    RetrievedPage,
    RunResult,
    RunStatus,
    VerificationReport,
    VerificationStatus,
    WorkflowEvent,
)


class Researcher(Protocol):
    async def research(
        self,
        request: ResearchRequest,
        *,
        max_passes: int,
    ) -> AgentSubmission: ...

    async def repair_package(
        self,
        request: ResearchRequest,
        submission: AgentSubmission,
        issues: list[str],
    ) -> AgentSubmission: ...

    async def research_gap(
        self,
        request: ResearchRequest,
        *,
        target_field: FieldName,
        unresolved_fields: list[FieldName],
        verifier_reasons: dict[FieldName, str],
        package: CompanyResearchPackage,
        attempted_urls: list[str],
    ) -> AgentSubmission: ...


class SemanticVerifier(Protocol):
    async def verify(
        self,
        request: ResearchRequest,
        package: CompanyResearchPackage,
        *,
        fields: list[FieldName],
    ) -> VerificationReport: ...


class ClaimRepairer(Protocol):
    async def repair(
        self,
        request: ResearchRequest,
        package: CompanyResearchPackage,
        verdict: FieldVerdict,
    ) -> ClaimRepairProposal: ...


class EvidenceStore:
    def __init__(self) -> None:
        self._pages: dict[str, RetrievedPage] = {}
        self._pages_by_id: dict[str, RetrievedPage] = {}

    def add(self, pages: Iterable[RetrievedPage]) -> None:
        for page in pages:
            self._pages[page.url] = page
            if page.page_id is not None:
                self._pages_by_id[page.page_id] = page

    def get(
        self,
        url: str,
        *,
        page_id: str | None = None,
    ) -> RetrievedPage | None:
        if page_id is not None:
            return self._pages_by_id.get(page_id)
        return self._pages.get(url)


class DeterministicGate:
    """Check package shape and evidence integrity without judging meaning."""

    def check(
        self,
        package: CompanyResearchPackage,
        request: ResearchRequest,
        store: EvidenceStore,
    ) -> list[GateIssue]:
        issues: list[GateIssue] = []
        allowed = {domain.lower() for domain in request.allowed_domains}

        for item in package.fields:
            for evidence in item.evidence:
                if evidence.page_id is None or not evidence.block_ids:
                    issues.append(
                        GateIssue(
                            field=item.field,
                            code="evidence_reference_missing",
                            detail=(
                                f"{item.field.value} evidence must identify a "
                                "captured page and at least one canonical block"
                            ),
                        )
                    )
                    continue

                hostname = (urlparse(evidence.url).hostname or "").lower()
                if not any(
                    hostname == domain or hostname.endswith(f".{domain}")
                    for domain in allowed
                ):
                    issues.append(
                        GateIssue(
                            field=item.field,
                            code="source_not_allowed",
                            detail=f"{evidence.url} is outside the source policy",
                        )
                    )
                    continue

                page = store.get(evidence.url, page_id=evidence.page_id)
                if page is None:
                    issues.append(
                        GateIssue(
                            field=item.field,
                            code="page_not_captured",
                            detail=f"no browser-tool result was captured for {evidence.url}",
                        )
                    )
                    continue

                if page.url != evidence.url:
                    issues.append(
                        GateIssue(
                            field=item.field,
                            code="page_reference_mismatch",
                            detail=(
                                f"{evidence.page_id} resolves to {page.url}, "
                                f"not {evidence.url}"
                            ),
                        )
                    )
                    continue

                if page.title != evidence.title:
                    issues.append(
                        GateIssue(
                            field=item.field,
                            code="source_metadata_mismatch",
                            detail=(
                                f"{evidence.page_id} resolves to title "
                                f"{page.title!r}, not {evidence.title!r}"
                            ),
                        )
                    )
                    continue

                if evidence.block_ids:
                    missing_blocks = [
                        block_id
                        for block_id in evidence.block_ids
                        if block_id not in page.blocks
                    ]
                    if missing_blocks:
                        issues.append(
                            GateIssue(
                                field=item.field,
                                code="block_not_captured",
                                detail=(
                                    f"{evidence.page_id} has no blocks "
                                    f"{missing_blocks}"
                                ),
                            )
                        )
                        continue
                    canonical = [
                        page.blocks[block_id]
                        for block_id in evidence.block_ids
                    ]
                    if evidence.passage not in canonical:
                        issues.append(
                            GateIssue(
                                field=item.field,
                                code="block_text_mismatch",
                                detail=(
                                    f"canonical blocks for {evidence.page_id} "
                                    "do not match the resolved passage"
                                ),
                            )
                        )
                        continue

                if evidence.passage not in page.text:
                    issues.append(
                        GateIssue(
                            field=item.field,
                            code="passage_not_found",
                            detail=(
                                f"the canonical block for {item.field.value} does "
                                f"not appear in the captured page {evidence.url}"
                            ),
                        )
                    )

        return issues


class VerifiedResearchLoop:
    """Run research until every field passes or the workflow escalates."""

    def __init__(
        self,
        researcher: Researcher,
        verifier: SemanticVerifier,
        claim_repairer: ClaimRepairer | None = None,
        *,
        max_research_passes: int = 3,
        max_schema_repairs: int = 1,
    ) -> None:
        self.researcher = researcher
        self.verifier = verifier
        self.claim_repairer = claim_repairer
        self.max_research_passes = max_research_passes
        self.max_schema_repairs = max_schema_repairs
        self.gate = DeterministicGate()

    async def run(self, request: ResearchRequest) -> RunResult:
        submission = await self.researcher.research(
            request,
            max_passes=self.max_research_passes,
        )
        return await self.run_from_submission(request, submission)

    async def run_from_submission(
        self,
        request: ResearchRequest,
        submission: AgentSubmission,
    ) -> RunResult:
        """Apply the quality loop to an already captured initial candidate."""
        store = EvidenceStore()
        events: list[WorkflowEvent] = []

        store.add(submission.pages)
        events.append(
            WorkflowEvent(
                stage="research",
                detail=(
                    f"researcher submitted after {len(submission.searches)} "
                    "captured searches"
                ),
            )
        )

        package, submission = await self._validated_package(
            request,
            submission,
            store,
            events,
        )
        if package is None:
            return self._human_review(
                package=None,
                report=None,
                unresolved=list(REQUIRED_FIELDS),
                reason="research package failed deterministic validation",
                events=events,
            )

        report = await self._verify(
            request,
            package,
            list(REQUIRED_FIELDS),
            events,
        )
        decision = self._accept_if_complete(package, report, events)
        if decision is not None:
            return decision

        attempted_urls = self._evidence_urls(package)
        attempted_repairs: set[FieldName] = set()
        attempted_searches: set[FieldName] = set()
        while True:
            repair_field = self._next_repair_field(
                report,
                attempted_repairs,
            )
            if repair_field is not None:
                attempted_repairs.add(repair_field)
                repaired = await self._attempt_claim_repair(
                    request,
                    package,
                    report.by_field()[repair_field],
                    events,
                )
                if repaired is not None:
                    package = repaired
                    partial = await self._verify(
                        request,
                        package,
                        [repair_field],
                        events,
                    )
                    report = self._merge_verification(report, partial)
                    decision = self._accept_if_complete(package, report, events)
                    if decision is not None:
                        return decision
                continue

            target_field = self._next_search_field(
                report,
                attempted_repairs,
                attempted_searches,
            )
            if target_field is None:
                break
            attempted_searches.add(target_field)
            unresolved = self._unresolved_fields(report)
            verifier_reasons = {
                field: report.by_field()[field].reason
                for field in unresolved
            }

            before = self._evidence_fingerprints(package, unresolved)
            gap_submission = await self.researcher.research_gap(
                request,
                target_field=target_field,
                unresolved_fields=unresolved,
                verifier_reasons=verifier_reasons,
                package=package,
                attempted_urls=sorted(attempted_urls),
            )
            store.add(gap_submission.pages)
            events.append(
                WorkflowEvent(
                    stage="targeted_research",
                    field=target_field,
                    detail=self._targeted_search_detail(gap_submission),
                )
            )

            update, gap_submission = await self._validated_package(
                request,
                gap_submission,
                store,
                events,
            )
            if update is None:
                events.append(
                    WorkflowEvent(
                        stage="desist",
                        field=target_field,
                        detail=(
                            "targeted research returned an invalid evidence "
                            "package"
                        ),
                    )
                )
                continue

            package = self._merge_unresolved(package, update, unresolved)
            attempted_urls.update(self._evidence_urls(package))
            after = self._evidence_fingerprints(package, unresolved)
            if after == before:
                events.append(
                    WorkflowEvent(
                        stage="desist",
                        field=target_field,
                        detail="targeted search produced no new admissible evidence",
                    )
                )
                continue

            partial = await self._verify(request, package, unresolved, events)
            report = self._merge_verification(report, partial)
            decision = self._accept_if_complete(package, report, events)
            if decision is not None:
                return decision

            if (
                report.by_field()[target_field].status
                is VerificationStatus.INSUFFICIENT
            ):
                events.append(
                    WorkflowEvent(
                        stage="desist",
                        field=target_field,
                        detail="field remained insufficient after its targeted search",
                    )
                )

        unresolved = self._unresolved_fields(report)
        details: list[str] = []
        conflicting = self._conflicting_fields(report)
        insufficient = self._insufficient_fields(report)
        if conflicting:
            details.append(
                "conflicting fields: "
                + ", ".join(field.value for field in conflicting)
            )
        if insufficient:
            details.append(
                "insufficient fields after targeted recovery: "
                + ", ".join(field.value for field in insufficient)
            )
        return self._human_review(
            package=package,
            report=report,
            unresolved=unresolved,
            reason="; ".join(details) or "research ended without full verification",
            events=events,
        )

    async def _validated_package(
        self,
        request: ResearchRequest,
        submission: AgentSubmission,
        store: EvidenceStore,
        events: list[WorkflowEvent],
    ) -> tuple[CompanyResearchPackage | None, AgentSubmission]:
        current = submission
        for attempt in range(self.max_schema_repairs + 1):
            errors: list[str] = []
            package: CompanyResearchPackage | None = None
            try:
                package = CompanyResearchPackage.model_validate_json(
                    current.package_json
                )
            except ValidationError as error:
                errors.extend(
                    f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                    for item in error.errors()
                )

            if package is not None:
                errors.extend(
                    f"{issue.code}: {issue.detail}"
                    for issue in self.gate.check(package, request, store)
                )

            if not errors:
                events.append(
                    WorkflowEvent(
                        stage="deterministic_gate",
                        detail="JSON schema and evidence-integrity checks passed",
                    )
                )
                return package, current

            events.append(
                WorkflowEvent(
                    stage="deterministic_gate",
                    detail="; ".join(errors),
                )
            )
            if attempt == self.max_schema_repairs:
                return None, current
            current = await self.researcher.repair_package(
                request,
                current,
                errors,
            )
            events.append(
                WorkflowEvent(
                    stage="package_repair",
                    detail="reconstructed exact passages from captured page text",
                )
            )
            store.add(current.pages)

        return None, current

    async def _verify(
        self,
        request: ResearchRequest,
        package: CompanyResearchPackage,
        fields: list[FieldName],
        events: list[WorkflowEvent],
    ) -> VerificationReport:
        report = await self.verifier.verify(request, package, fields=fields)
        returned = {item.field for item in report.verdicts}
        expected = set(fields)
        if returned != expected:
            missing = sorted(item.value for item in expected - returned)
            extra = sorted(item.value for item in returned - expected)
            raise ValueError(
                f"verifier returned the wrong fields; missing={missing}, extra={extra}"
            )

        events.append(
            WorkflowEvent(
                stage="semantic_verification",
                detail=", ".join(
                    f"{item.field.value}={item.status.value}"
                    for item in report.verdicts
                ),
            )
        )
        return report

    def _next_repair_field(
        self,
        report: VerificationReport,
        attempted_repairs: set[FieldName],
    ) -> FieldName | None:
        if self.claim_repairer is None:
            return None
        verdicts = report.by_field()
        return next(
            (
                field
                for field in REQUIRED_FIELDS
                if field not in attempted_repairs
                and verdicts[field].status is VerificationStatus.INSUFFICIENT
                and verdicts[field].next_action
                is RecoveryAction.REPAIR_CLAIM
            ),
            None,
        )

    def _next_search_field(
        self,
        report: VerificationReport,
        attempted_repairs: set[FieldName],
        attempted_searches: set[FieldName],
    ) -> FieldName | None:
        verdicts = report.by_field()
        for field in REQUIRED_FIELDS:
            verdict = verdicts[field]
            if (
                field in attempted_searches
                or verdict.status is not VerificationStatus.INSUFFICIENT
                or verdict.next_action is RecoveryAction.HUMAN_REVIEW
            ):
                continue
            if verdict.next_action is RecoveryAction.SEARCH_EVIDENCE:
                return field
            if (
                verdict.next_action is RecoveryAction.REPAIR_CLAIM
                and (
                    self.claim_repairer is None
                    or field in attempted_repairs
                )
            ):
                return field
        return None

    async def _attempt_claim_repair(
        self,
        request: ResearchRequest,
        package: CompanyResearchPackage,
        verdict: FieldVerdict,
        events: list[WorkflowEvent],
    ) -> CompanyResearchPackage | None:
        if self.claim_repairer is None:
            return None
        proposal = await self.claim_repairer.repair(
            request,
            package,
            verdict,
        )
        item = package.by_field()[verdict.field]
        error = self._claim_repair_error(item, proposal)
        if error is not None:
            events.append(
                WorkflowEvent(
                    stage="claim_repair_rejected",
                    field=verdict.field,
                    detail=error,
                )
            )
            return None

        assert proposal.repaired_claim is not None
        fields = package.by_field()
        fields[verdict.field] = FieldSubmission(
            field=verdict.field,
            claim=proposal.repaired_claim,
            evidence=item.evidence,
        )
        events.append(
            WorkflowEvent(
                stage="claim_repair",
                field=verdict.field,
                detail=(
                    f"narrowed claim from {item.claim!r} to "
                    f"{proposal.repaired_claim!r}"
                ),
            )
        )
        return CompanyResearchPackage(
            company_identity=package.company_identity,
            fields=[fields[field] for field in REQUIRED_FIELDS],
        )

    @classmethod
    def _claim_repair_error(
        cls,
        item: FieldSubmission,
        proposal: ClaimRepairProposal,
    ) -> str | None:
        if proposal.field is not item.field:
            return "claim repair returned the wrong field"
        if proposal.original_claim != item.claim:
            return "claim repair did not preserve the original claim"
        if proposal.repaired_claim is None:
            return "claim repairer found no safe deletion-only repair"
        if not cls._is_strict_deletion(item.claim, proposal.repaired_claim):
            return "repaired claim must only delete words from the original"
        return None

    @staticmethod
    def _is_strict_deletion(original: str, repaired: str) -> bool:
        original_tokens = re.findall(r"[a-z0-9]+", original.casefold())
        repaired_tokens = re.findall(r"[a-z0-9]+", repaired.casefold())
        if not repaired_tokens or repaired_tokens == original_tokens:
            return False
        position = 0
        for token in repaired_tokens:
            try:
                position = original_tokens.index(token, position) + 1
            except ValueError:
                return False
        return True

    def _accept_if_complete(
        self,
        package: CompanyResearchPackage,
        report: VerificationReport,
        events: list[WorkflowEvent],
    ) -> RunResult | None:
        if all(
            item.status is VerificationStatus.VERIFIED
            for item in report.verdicts
        ):
            events.append(
                WorkflowEvent(
                    stage="accepted",
                    detail="every required field passed semantic verification",
                )
            )
            return RunResult(
                status=RunStatus.ACCEPTED,
                package=package,
                verification=report,
                unresolved_fields=[],
                events=events,
            )
        return None

    @staticmethod
    def _conflicting_fields(report: VerificationReport) -> list[FieldName]:
        return [
            item.field
            for item in report.verdicts
            if item.status is VerificationStatus.CONFLICTING
        ]

    @staticmethod
    def _insufficient_fields(report: VerificationReport) -> list[FieldName]:
        return [
            item.field
            for item in report.verdicts
            if item.status is VerificationStatus.INSUFFICIENT
        ]

    @staticmethod
    def _unresolved_fields(report: VerificationReport) -> list[FieldName]:
        verdicts = report.by_field()
        return [
            field
            for field in REQUIRED_FIELDS
            if verdicts[field].status is not VerificationStatus.VERIFIED
        ]

    @staticmethod
    def _evidence_urls(package: CompanyResearchPackage) -> set[str]:
        return {
            evidence.url
            for item in package.fields
            for evidence in item.evidence
        }

    @staticmethod
    def _evidence_fingerprints(
        package: CompanyResearchPackage,
        fields: list[FieldName],
    ) -> set[tuple[FieldName, str, str, str]]:
        selected = set(fields)
        return {
            (item.field, item.claim, evidence.url, evidence.passage)
            for item in package.fields
            if item.field in selected
            for evidence in item.evidence
        }

    @staticmethod
    def _merge_unresolved(
        current: CompanyResearchPackage,
        update: CompanyResearchPackage,
        unresolved: list[FieldName],
    ) -> CompanyResearchPackage:
        current_fields = current.by_field()
        update_fields = update.by_field()
        unresolved_set = set(unresolved)
        merged = [
            update_fields[name] if name in unresolved_set else current_fields[name]
            for name in REQUIRED_FIELDS
        ]
        return CompanyResearchPackage(
            company_identity=current.company_identity,
            fields=merged,
        )

    @staticmethod
    def _targeted_search_detail(submission: AgentSubmission) -> str:
        if not submission.searches:
            return "gap researcher returned without a web search"
        return f"gap researcher used: {submission.searches[0]}"

    @staticmethod
    def _merge_verification(
        current: VerificationReport,
        update: VerificationReport,
    ) -> VerificationReport:
        verdicts = current.by_field()
        verdicts.update(update.by_field())
        return VerificationReport(
            verdicts=[
                verdicts[field] for field in REQUIRED_FIELDS if field in verdicts
            ]
        )

    @staticmethod
    def _human_review(
        *,
        package: CompanyResearchPackage | None,
        report: VerificationReport | None,
        unresolved: list[FieldName],
        reason: str,
        events: list[WorkflowEvent],
    ) -> RunResult:
        events.append(
            WorkflowEvent(
                stage="human_review",
                detail=reason,
            )
        )
        return RunResult(
            status=RunStatus.HUMAN_REVIEW,
            package=package,
            verification=report,
            unresolved_fields=unresolved,
            human_review_reason=reason,
            events=events,
        )
