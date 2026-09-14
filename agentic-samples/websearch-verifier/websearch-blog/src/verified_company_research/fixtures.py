from __future__ import annotations

import re
from enum import StrEnum

from .contracts import (
    AgentSubmission,
    ClaimRepairProposal,
    CompanyResearchPackage,
    FieldName,
    FieldSubmission,
    FieldVerdict,
    ResearchRequest,
    RecoveryAction,
    RetrievedPage,
    SourceEvidence,
    VerificationReport,
    VerificationStatus,
)


class Scenario(StrEnum):
    IMMEDIATE_ACCEPTANCE = "immediate_acceptance"
    GAP_RESOLVED = "gap_resolved"
    GAP_UNRESOLVED = "gap_unresolved"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    CONFLICT_AND_GAP = "conflict_and_gap"
    MULTIPLE_GAPS = "multiple_gaps"
    CLAIM_REPAIR = "claim_repair"


ABOUT = RetrievedPage(
    url="https://acme.example/about",
    title="About Acme Analytics",
    text=(
        "Acme Analytics was founded in 2018. "
        "Acme Analytics is headquartered in London, United Kingdom."
    ),
    page_id="page_about",
    blocks={
        "b0001": "Acme Analytics was founded in 2018.",
        "b0002": (
            "Acme Analytics is headquartered in London, United Kingdom."
        ),
    },
)
OFFICE = RetrievedPage(
    url="https://acme.example/london-office",
    title="Acme Analytics opens a London office",
    text="Acme Analytics opened a London office in 2020.",
    page_id="page_office",
    blocks={"b0001": "Acme Analytics opened a London office in 2020."},
)
PRODUCT = RetrievedPage(
    url="https://acme.example/beacon",
    title="Beacon",
    text=(
        "Acme Analytics offers Beacon. "
        "Beacon monitors cloud infrastructure and alerts teams to service risks."
    ),
    page_id="page_product",
    blocks={
        "b0001": "Acme Analytics offers Beacon.",
        "b0002": (
            "Beacon monitors cloud infrastructure and alerts teams to service risks."
        ),
    },
)
REGISTRY_CONFLICT = RetrievedPage(
    url="https://registry.example/acme-analytics",
    title="Acme Analytics company record",
    text="The registry record states that Acme Analytics was founded in 2019.",
    page_id="page_registry_conflict",
    blocks={
        "b0001": (
            "The registry record states that Acme Analytics was founded in 2019."
        )
    },
)

REQUEST = ResearchRequest(
    company_name="Acme Analytics",
    website="https://acme.example",
    allowed_domains=["acme.example", "registry.example"],
)


def evidence(page: RetrievedPage, passage: str) -> SourceEvidence:
    block_id = next(
        (
            block_id
            for block_id, block_text in page.blocks.items()
            if block_text == passage
        ),
        None,
    )
    if page.page_id is None or block_id is None:
        raise ValueError("fixture evidence must resolve to one canonical block")
    return SourceEvidence(
        url=page.url,
        title=page.title,
        passage=passage,
        page_id=page.page_id,
        block_ids=[block_id],
    )


def package(
    *,
    headquarters_page: RetrievedPage = ABOUT,
    headquarters_passage: str = (
        "Acme Analytics is headquartered in London, United Kingdom."
    ),
    founded_evidence: list[SourceEvidence] | None = None,
) -> CompanyResearchPackage:
    return CompanyResearchPackage(
        company_identity="Acme Analytics (https://acme.example)",
        fields=[
            FieldSubmission(
                field=FieldName.NAME,
                claim="Acme Analytics",
                evidence=[
                    evidence(
                        ABOUT,
                        "Acme Analytics was founded in 2018.",
                    )
                ],
            ),
            FieldSubmission(
                field=FieldName.HEADQUARTERS,
                claim="London, United Kingdom",
                evidence=[
                    evidence(
                        headquarters_page,
                        headquarters_passage,
                    )
                ],
            ),
            FieldSubmission(
                field=FieldName.FOUNDED_YEAR,
                claim="2018",
                evidence=founded_evidence
                or [
                    evidence(
                        ABOUT,
                        "Acme Analytics was founded in 2018.",
                    )
                ],
            ),
            FieldSubmission(
                field=FieldName.PRODUCT_NAME,
                claim="Beacon",
                evidence=[
                    evidence(
                        PRODUCT,
                        "Acme Analytics offers Beacon.",
                    )
                ],
            ),
            FieldSubmission(
                field=FieldName.PRODUCT_DESCRIPTION,
                claim=(
                    "Beacon monitors cloud infrastructure and alerts teams "
                    "to service risks."
                ),
                evidence=[
                    evidence(
                        PRODUCT,
                        (
                            "Beacon monitors cloud infrastructure and alerts "
                            "teams to service risks."
                        ),
                    )
                ],
            ),
        ],
    )


class FixtureResearcher:
    """Return controlled packages while recording the loop instructions."""

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.initial_max_passes: int | None = None
        self.initial_calls = 0
        self.gap_targets: list[FieldName] = []
        self.gap_unresolved_sets: list[list[FieldName]] = []
        self.gap_verifier_reasons: list[dict[FieldName, str]] = []

    async def research(
        self,
        request: ResearchRequest,
        *,
        max_passes: int,
    ) -> AgentSubmission:
        self.initial_calls += 1
        self.initial_max_passes = max_passes
        if self.scenario in {
            Scenario.CONFLICTING_EVIDENCE,
            Scenario.CONFLICT_AND_GAP,
        }:
            candidate = package(
                headquarters_page=(
                    OFFICE
                    if self.scenario is Scenario.CONFLICT_AND_GAP
                    else ABOUT
                ),
                headquarters_passage=(
                    "Acme Analytics opened a London office in 2020."
                    if self.scenario is Scenario.CONFLICT_AND_GAP
                    else "Acme Analytics is headquartered in London, United Kingdom."
                ),
                founded_evidence=[
                    evidence(ABOUT, "Acme Analytics was founded in 2018."),
                    evidence(
                        REGISTRY_CONFLICT,
                        (
                            "The registry record states that Acme Analytics "
                            "was founded in 2019."
                        ),
                    ),
                ]
            )
            pages = [ABOUT, OFFICE, PRODUCT, REGISTRY_CONFLICT]
        elif self.scenario is Scenario.MULTIPLE_GAPS:
            candidate = package(
                headquarters_page=OFFICE,
                headquarters_passage=(
                    "Acme Analytics opened a London office in 2020."
                ),
            )
            candidate.by_field()[FieldName.PRODUCT_NAME].evidence = [
                evidence(OFFICE, "Acme Analytics opened a London office in 2020.")
            ]
            pages = [ABOUT, OFFICE, PRODUCT]
        elif self.scenario in {
            Scenario.GAP_RESOLVED,
            Scenario.GAP_UNRESOLVED,
        }:
            candidate = package(
                headquarters_page=OFFICE,
                headquarters_passage=(
                    "Acme Analytics opened a London office in 2020."
                ),
            )
            pages = [ABOUT, OFFICE, PRODUCT]
        elif self.scenario is Scenario.CLAIM_REPAIR:
            candidate = package()
            candidate.by_field()[FieldName.PRODUCT_DESCRIPTION].claim = (
                "Beacon monitors cloud infrastructure and alerts teams to "
                "service risks. It was launched in 2015."
            )
            pages = [ABOUT, PRODUCT]
        else:
            candidate = package()
            pages = [ABOUT, PRODUCT]

        return AgentSubmission(
            package_json=candidate.model_dump_json(),
            pages=pages,
            searches=[
                "Acme Analytics company facts",
                "Acme Analytics Beacon product",
            ],
        )

    async def repair_package(
        self,
        request: ResearchRequest,
        submission: AgentSubmission,
        issues: list[str],
    ) -> AgentSubmission:
        return submission

    async def research_gap(
        self,
        request: ResearchRequest,
        *,
        target_field: FieldName,
        unresolved_fields: list[FieldName],
        verifier_reasons: dict[FieldName, str],
        package: CompanyResearchPackage,
        attempted_urls: list[str],
    ) -> AgentSubmission:
        self.gap_targets.append(target_field)
        self.gap_unresolved_sets.append(list(unresolved_fields))
        self.gap_verifier_reasons.append(dict(verifier_reasons))

        if self.scenario in {
            Scenario.GAP_RESOLVED,
            Scenario.CONFLICT_AND_GAP,
        }:
            candidate = package_with_replaced_headquarters(package, ABOUT)
            pages = [ABOUT]
        else:
            candidate = package
            pages = [OFFICE]

        return AgentSubmission(
            package_json=candidate.model_dump_json(),
            pages=pages,
            searches=[
                (
                    '"Acme Analytics" headquarters official company '
                    "site:acme.example"
                )
            ],
        )


def package_with_replaced_headquarters(
    current: CompanyResearchPackage,
    page: RetrievedPage,
) -> CompanyResearchPackage:
    fields = current.by_field()
    fields[FieldName.HEADQUARTERS] = FieldSubmission(
        field=FieldName.HEADQUARTERS,
        claim="London, United Kingdom",
        evidence=[
            evidence(
                page,
                "Acme Analytics is headquartered in London, United Kingdom.",
            )
        ],
    )
    return CompanyResearchPackage(
        company_identity=current.company_identity,
        fields=[fields[name] for name in FieldName],
    )


class FixtureSemanticVerifier:
    """Deterministic test double for the model-based semantic verifier."""

    async def verify(
        self,
        request: ResearchRequest,
        candidate: CompanyResearchPackage,
        *,
        fields: list[FieldName],
    ) -> VerificationReport:
        by_field = candidate.by_field()
        return VerificationReport(
            verdicts=[
                self._verify_field(by_field[field])
                for field in fields
            ]
        )

    def _verify_field(self, item: FieldSubmission) -> FieldVerdict:
        passages = [source.passage for source in item.evidence]
        checked_urls = [source.url for source in item.evidence]
        normalized = [passage.lower() for passage in passages]
        claim = item.claim.lower()

        if item.field is FieldName.FOUNDED_YEAR:
            asserted_years = {
                match
                for passage in normalized
                for match in re.findall(r"founded in (\d{4})", passage)
            }
            if len(asserted_years) > 1:
                return FieldVerdict(
                    field=item.field,
                    status=VerificationStatus.CONFLICTING,
                    next_action=RecoveryAction.HUMAN_REVIEW,
                    reason="The cited passages assert different founding years.",
                    checked_urls=checked_urls,
                )
            supported = f"founded in {claim}" in " ".join(normalized)
        elif item.field is FieldName.HEADQUARTERS:
            supported = any(
                marker in passage
                for passage in normalized
                for marker in (
                    f"headquartered in {claim}",
                    f"headquarters are in {claim}",
                )
            )
        elif item.field is FieldName.PRODUCT_NAME:
            supported = any(
                f"offers {claim}" in passage
                or f"product {claim}" in passage
                for passage in normalized
            )
        else:
            supported = any(claim in passage for passage in normalized)

        return FieldVerdict(
            field=item.field,
            status=(
                VerificationStatus.VERIFIED
                if supported
                else VerificationStatus.INSUFFICIENT
            ),
            next_action=(
                RecoveryAction.NONE
                if supported
                else (
                    RecoveryAction.REPAIR_CLAIM
                    if item.field is FieldName.PRODUCT_DESCRIPTION
                    and any(
                        passage in claim and passage != claim
                        for passage in normalized
                    )
                    else RecoveryAction.SEARCH_EVIDENCE
                )
            ),
            reason=(
                "The passage states the claim and field relationship explicitly."
                if supported
                else "The passage does not explicitly support this field relationship."
            ),
            checked_urls=checked_urls,
        )


class FixtureClaimRepairer:
    def __init__(self) -> None:
        self.fields: list[FieldName] = []

    async def repair(
        self,
        request: ResearchRequest,
        candidate: CompanyResearchPackage,
        verdict: FieldVerdict,
    ) -> ClaimRepairProposal:
        self.fields.append(verdict.field)
        item = candidate.by_field()[verdict.field]
        repaired = next(
            (
                source.passage
                for source in item.evidence
                if source.passage.casefold() in item.claim.casefold()
            ),
            None,
        )
        return ClaimRepairProposal(
            field=verdict.field,
            original_claim=item.claim,
            repaired_claim=repaired,
            reason=(
                "Use the supported passage as the narrower claim."
                if repaired is not None
                else "No deletion-only repair is available."
            ),
        )
