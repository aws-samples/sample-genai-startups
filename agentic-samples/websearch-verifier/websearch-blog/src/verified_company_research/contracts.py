from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldName(StrEnum):
    NAME = "name"
    HEADQUARTERS = "headquarters"
    FOUNDED_YEAR = "founded_year"
    PRODUCT_NAME = "product_name"
    PRODUCT_DESCRIPTION = "product_description"


REQUIRED_FIELDS = tuple(FieldName)


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"


class RecoveryAction(StrEnum):
    NONE = "none"
    REPAIR_CLAIM = "repair_claim"
    SEARCH_EVIDENCE = "search_evidence"
    HUMAN_REVIEW = "human_review"


class RunStatus(StrEnum):
    ACCEPTED = "accepted"
    HUMAN_REVIEW = "human_review"


class SourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: Annotated[str, Field(min_length=1)]
    passage: Annotated[str, Field(min_length=1)]
    page_id: str | None = None
    block_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_https_url(self) -> "SourceEvidence":
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("evidence URL must be an absolute HTTPS URL")
        return self


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: Annotated[str, Field(min_length=1)]
    block_ids: Annotated[list[str], Field(min_length=1)]

    @model_validator(mode="after")
    def require_unique_blocks(self) -> "EvidenceReference":
        if len(self.block_ids) != len(set(self.block_ids)):
            raise ValueError("evidence reference contains duplicate block IDs")
        return self


class FieldReferenceSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldName
    claim: Annotated[str, Field(min_length=1)]
    evidence: Annotated[list[EvidenceReference], Field(min_length=1)]


class CompanyResearchReferencePackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_identity: Annotated[str, Field(min_length=1)]
    fields: Annotated[
        list[FieldReferenceSubmission],
        Field(min_length=5, max_length=5),
    ]

    @model_validator(mode="after")
    def require_each_field_once(self) -> "CompanyResearchReferencePackage":
        names = [item.field for item in self.fields]
        if set(names) != set(REQUIRED_FIELDS) or len(names) != len(REQUIRED_FIELDS):
            raise ValueError("reference package must contain each field exactly once")
        return self


class FieldSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldName
    claim: Annotated[str, Field(min_length=1)]
    evidence: Annotated[list[SourceEvidence], Field(min_length=1)]


class CompanyResearchPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_identity: Annotated[str, Field(min_length=1)]
    fields: Annotated[list[FieldSubmission], Field(min_length=5, max_length=5)]

    @model_validator(mode="after")
    def require_each_field_once(self) -> "CompanyResearchPackage":
        names = [item.field for item in self.fields]
        missing = set(REQUIRED_FIELDS) - set(names)
        duplicates = {name for name in names if names.count(name) > 1}
        if missing or duplicates:
            details: list[str] = []
            if missing:
                details.append(
                    "missing " + ", ".join(sorted(item.value for item in missing))
                )
            if duplicates:
                details.append(
                    "duplicate "
                    + ", ".join(sorted(item.value for item in duplicates))
                )
            raise ValueError("; ".join(details))
        return self

    def by_field(self) -> dict[FieldName, FieldSubmission]:
        return {item.field: item for item in self.fields}


class RetrievedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str
    text: str
    page_id: str | None = None
    blocks: dict[str, str] = Field(default_factory=dict)


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: Annotated[str, Field(min_length=1)]
    website: str | None = None
    allowed_domains: Annotated[list[str], Field(min_length=1)]


class AgentSubmission(BaseModel):
    """Raw agent output plus pages captured by the browser-tool wrapper."""

    model_config = ConfigDict(extra="forbid")

    package_json: str
    pages: list[RetrievedPage]
    searches: list[str] = Field(default_factory=list)


class GateIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldName | None
    code: str
    detail: str


class FieldVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldName
    status: VerificationStatus
    next_action: RecoveryAction
    reason: Annotated[str, Field(min_length=1)]
    checked_urls: list[str]

    @model_validator(mode="after")
    def require_valid_action_for_status(self) -> "FieldVerdict":
        allowed = {
            VerificationStatus.VERIFIED: {RecoveryAction.NONE},
            VerificationStatus.INSUFFICIENT: {
                RecoveryAction.REPAIR_CLAIM,
                RecoveryAction.SEARCH_EVIDENCE,
                RecoveryAction.HUMAN_REVIEW,
            },
            VerificationStatus.CONFLICTING: {RecoveryAction.HUMAN_REVIEW},
        }
        if self.next_action not in allowed[self.status]:
            raise ValueError(
                f"{self.status.value} cannot use next_action "
                f"{self.next_action.value}"
            )
        return self


class ClaimRepairProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldName
    original_claim: Annotated[str, Field(min_length=1)]
    repaired_claim: Annotated[str, Field(min_length=1)] | None = None
    reason: Annotated[str, Field(min_length=1)]


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[FieldVerdict]

    @model_validator(mode="after")
    def prevent_duplicate_fields(self) -> "VerificationReport":
        fields = [item.field for item in self.verdicts]
        if len(fields) != len(set(fields)):
            raise ValueError("verification report contains duplicate fields")
        return self

    def by_field(self) -> dict[FieldName, FieldVerdict]:
        return {item.field: item for item in self.verdicts}


class WorkflowEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    detail: str
    field: FieldName | None = None


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RunStatus
    package: CompanyResearchPackage | None
    verification: VerificationReport | None
    unresolved_fields: list[FieldName]
    human_review_reason: str | None = None
    events: list[WorkflowEvent]
