from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .contracts import (
    AgentSubmission,
    ClaimRepairProposal,
    CompanyResearchReferencePackage,
    CompanyResearchPackage,
    FieldName,
    FieldSubmission,
    FieldVerdict,
    REQUIRED_FIELDS,
    ResearchRequest,
    RecoveryAction,
    RunStatus,
    SourceEvidence,
    VerificationReport,
)
from .live_browser import (
    AgentCoreBrowserCapture,
    PageArtifact,
)
from .loop import VerifiedResearchLoop
from .source_quality import SourceQualityPolicy


FIELD_RULES = """
Apply these rules literally:
- name: the passage explicitly names the current company or trading brand.
- headquarters: the passage explicitly says headquarters, headquartered, or
  head office. A store, factory, office, registered office, or address alone is
  insufficient.
- founded_year: the passage explicitly says founded or established in that
  year. Incorporation, invention, launch, and first-production dates do not
  establish this field.
- product_name: the passage explicitly identifies a product made, sold, or
  offered by this company.
- product_description: the passage explicitly explains what the cited product
  is or does, and it must refer to the same product as product_name.
Two passages conflict only when they explicitly assert incompatible values for
one field. Do not resolve a conflict by preference or inference.
""".strip()

NATIVE_RESEARCH_SKILL = "company-research"


def _native_skill_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / ".claude"
        / "skills"
        / NATIVE_RESEARCH_SKILL
        / "SKILL.md"
    )


def _native_skill_sha256() -> str:
    return hashlib.sha256(_native_skill_path().read_bytes()).hexdigest()


def _validate_implementation_hashes(registration: dict[str, Any]) -> None:
    project_root = Path(__file__).resolve().parents[2]
    for relative_path, expected in registration.get(
        "implementation_sha256", {}
    ).items():
        actual = hashlib.sha256((project_root / relative_path).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"{relative_path} changed after registration: "
                f"registered={expected}, actual={actual}"
            )


class ReviewLabel(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    UNRESOLVED = "unresolved"


class ReviewVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldName
    label: ReviewLabel
    reason: str = Field(min_length=1)
    checked_urls: list[str]


class CandidateReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    verdicts: list[ReviewVerdict]

    @model_validator(mode="after")
    def require_all_fields(self) -> "CandidateReview":
        fields = [item.field for item in self.verdicts]
        if set(fields) != set(REQUIRED_FIELDS) or len(fields) != len(REQUIRED_FIELDS):
            raise ValueError("review must contain each ontology field exactly once")
        return self


class BlindedReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviews: list[CandidateReview] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def require_two_candidates(self) -> "BlindedReviewReport":
        ids = [item.candidate_id for item in self.reviews]
        if len(set(ids)) != 2:
            raise ValueError("review must contain two distinct candidate IDs")
        return self


class UsageLog:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def add(self, phase: str, model: str, result: Any) -> None:
        totals = {
            "input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
        }
        for usage in (getattr(result, "model_usage", None) or {}).values():
            totals["input_tokens"] += int(usage.get("inputTokens", 0))
            totals["cache_read_input_tokens"] += int(
                usage.get("cacheReadInputTokens", 0)
            )
            totals["cache_creation_input_tokens"] += int(
                usage.get("cacheCreationInputTokens", 0)
            )
            totals["output_tokens"] += int(usage.get("outputTokens", 0))
            totals["thinking_tokens"] += int(usage.get("thinkingTokens", 0))
        self.calls.append(
            {
                "phase": phase,
                "model": model,
                **totals,
                "turns": int(getattr(result, "num_turns", 0)),
                "duration_ms": int(getattr(result, "duration_ms", 0)),
                "duration_api_ms": int(getattr(result, "duration_api_ms", 0)),
                "estimated_cost_usd": getattr(result, "total_cost_usd", None),
                "session_id": getattr(result, "session_id", None),
                "stop_reason": getattr(result, "stop_reason", None),
            }
        )

    def snapshot(self) -> dict[str, Any]:
        numeric = (
            "input_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "output_tokens",
            "thinking_tokens",
            "turns",
            "duration_ms",
            "duration_api_ms",
        )
        totals = {name: sum(int(call[name]) for call in self.calls) for name in numeric}
        costs = [
            float(call["estimated_cost_usd"])
            for call in self.calls
            if call["estimated_cost_usd"] is not None
        ]
        return {
            **totals,
            "estimated_cost_usd": sum(costs) if costs else None,
            "calls": self.calls,
        }


async def _structured_query(
    *,
    prompt: str,
    options: Any,
    phase: str,
    model: str,
    usage: UsageLog,
) -> dict[str, Any]:
    from claude_agent_sdk import ResultMessage, query

    result: ResultMessage | None = None
    async with asyncio.timeout(900):
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result = message
    if result is None:
        raise RuntimeError(f"{phase} returned no ResultMessage")
    usage.add(phase, model, result)
    if result.is_error:
        raise RuntimeError(
            f"{phase} failed: "
            + ("; ".join(result.errors or []) or str(result.result))
        )
    if not isinstance(result.structured_output, dict):
        raise RuntimeError(f"{phase} returned no structured output")
    return result.structured_output


def _bedrock_env(profile: str, region: str) -> dict[str, str]:
    import boto3

    credentials = boto3.Session(
        profile_name=profile,
        region_name=region,
    ).get_credentials()
    if credentials is None:
        raise RuntimeError(f"AWS profile {profile} returned no credentials")
    frozen = credentials.get_frozen_credentials()
    os.environ.pop("AWS_PROFILE", None)
    os.environ.pop("AWS_DEFAULT_PROFILE", None)
    env = {
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "AWS_REGION": region,
        "AWS_DEFAULT_REGION": region,
        "AWS_ACCESS_KEY_ID": frozen.access_key,
        "AWS_SECRET_ACCESS_KEY": frozen.secret_key,
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    if frozen.token:
        env["AWS_SESSION_TOKEN"] = frozen.token
    return env


def _options(
    *,
    model: str,
    env: dict[str, str],
    schema: dict[str, Any],
    system_prompt: str,
    max_turns: int,
    mcp_servers: dict[str, Any] | None = None,
    tools: list[str] | None = None,
    skills: list[str] | None = None,
) -> Any:
    from claude_agent_sdk import ClaudeAgentOptions

    tool_names = tools or []
    skill_names = skills or []
    return ClaudeAgentOptions(
        cwd=Path(__file__).resolve().parents[2],
        setting_sources=["project"] if skill_names else [],
        skills=skill_names,
        tools=tool_names,
        allowed_tools=tool_names,
        mcp_servers=mcp_servers or {},
        strict_mcp_config=True,
        permission_mode="dontAsk",
        model=model,
        max_turns=max_turns,
        output_format={"type": "json_schema", "schema": schema},
        system_prompt=system_prompt,
        env=env,
    )


def _research_prompt(
    request: ResearchRequest,
    *,
    max_passes: int,
) -> str:
    return f"""
Use the {NATIVE_RESEARCH_SKILL} skill to research {request.company_name}.
Return the requested five-field JSON package. You may use no more than
{max_passes} focused searches.

Task configuration:
{request.model_dump_json(indent=2)}
""".strip()


def _resolve_reference_package(
    document: dict[str, Any],
    browser: AgentCoreBrowserCapture,
) -> CompanyResearchPackage:
    reference_package = CompanyResearchReferencePackage.model_validate(document)
    fields = []
    for field in reference_package.fields:
        evidence = []
        seen: set[tuple[str, str]] = set()
        for reference in field.evidence:
            page = browser.page_by_id(reference.page_id)
            if page is None:
                raise ValueError(
                    f"unknown page_id for {field.field.value}: {reference.page_id}"
                )
            blocks = {
                block["block_id"]: block["text"]
                for block in page.blocks
            }
            for block_id in reference.block_ids:
                if block_id not in blocks:
                    raise ValueError(
                        f"unknown block_id for {reference.page_id}: {block_id}"
                    )
                key = (reference.page_id, block_id)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    SourceEvidence(
                        url=page.url,
                        title=page.title,
                        passage=blocks[block_id],
                        page_id=page.page_id,
                        block_ids=[block_id],
                    )
                )
        fields.append(
            FieldSubmission(
                field=field.field,
                claim=field.claim,
                evidence=evidence,
            )
        )
    return CompanyResearchPackage(
        company_identity=reference_package.company_identity,
        fields=fields,
    )


def _reference_document(package: CompanyResearchPackage) -> dict[str, Any]:
    fields = []
    for field in package.fields:
        references: dict[str, list[str]] = {}
        for evidence in field.evidence:
            if evidence.page_id is None or not evidence.block_ids:
                raise ValueError(
                    f"{field.field.value} contains evidence without block references"
                )
            block_ids = references.setdefault(evidence.page_id, [])
            for block_id in evidence.block_ids:
                if block_id not in block_ids:
                    block_ids.append(block_id)
        fields.append(
            {
                "field": field.field.value,
                "claim": field.claim,
                "evidence": [
                    {"page_id": page_id, "block_ids": block_ids}
                    for page_id, block_ids in references.items()
                ],
            }
        )
    return {
        "company_identity": package.company_identity,
        "fields": fields,
    }


class LiveResearcher:
    def __init__(
        self,
        *,
        browser: AgentCoreBrowserCapture,
        initial_model: str,
        recovery_model: str,
        env: dict[str, str],
        usage: UsageLog,
        source_policy: SourceQualityPolicy,
        initial_max_turns: int,
        run_label: str,
    ) -> None:
        self.browser = browser
        self.initial_model = initial_model
        self.recovery_model = recovery_model
        self.env = env
        self.usage = usage
        self.source_policy = source_policy
        self.initial_max_turns = initial_max_turns
        self.run_label = run_label

    async def research(
        self,
        request: ResearchRequest,
        *,
        max_passes: int,
    ) -> AgentSubmission:
        server = self.browser.tool_server(search_limit=max_passes)
        tools = ["mcp__live_web__search_web", "mcp__live_web__read_page"]
        prompt = _research_prompt(
            request,
            max_passes=max_passes,
        )
        document = await _structured_query(
            prompt=prompt,
            options=_options(
                model=self.initial_model,
                env=self.env,
                schema=CompanyResearchReferencePackage.model_json_schema(),
                system_prompt=(
                    "You are the initial company researcher. Return only facts "
                    "supported by captured web pages."
                ),
                max_turns=self.initial_max_turns,
                mcp_servers={"live_web": server},
                tools=tools,
                skills=[NATIVE_RESEARCH_SKILL],
            ),
            phase=f"{self.run_label}_initial_research",
            model=self.initial_model,
            usage=self.usage,
        )
        return self._submission(document)

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
        server = self.browser.tool_server(search_limit=1)
        tools = ["mcp__live_web__search_web", "mcp__live_web__read_page"]
        prompt = f"""
Run exactly one narrowly targeted search for {target_field.value} at
{request.company_name}. Read only results needed to inspect that field. Check
any newly captured evidence blocks against every unresolved field before
finishing.
Use the verifier's reason for {target_field.value} as the search specification;
do not repeat broad company research.
Return the complete package, changing only unresolved fields for which the new
page provides explicit support. Cite only page_id and block_ids returned by
read_page; never copy or rewrite source text. If the search does not resolve a
field, preserve its existing claim and evidence references. Never invent a
replacement.

{FIELD_RULES}

Source-quality contract:
{self.source_policy.prompt_text()}

Unresolved fields:
{json.dumps([field.value for field in unresolved_fields])}

Verifier findings:
{json.dumps(
    {field.value: reason for field, reason in verifier_reasons.items()},
    indent=2,
)}

URLs already checked:
{json.dumps(attempted_urls, indent=2)}

Current package:
{json.dumps(_reference_document(package), indent=2)}
""".strip()
        document = await _structured_query(
            prompt=prompt,
            options=_options(
                model=self.recovery_model,
                env=self.env,
                schema=CompanyResearchReferencePackage.model_json_schema(),
                system_prompt=(
                    "You are a targeted evidence researcher. One search is "
                    "available; do not broaden the task."
                ),
                max_turns=8,
                mcp_servers={"live_web": server},
                tools=tools,
            ),
            phase=f"targeted_research:{target_field.value}",
            model=self.recovery_model,
            usage=self.usage,
        )
        submission = self._submission(document)
        if len(submission.searches) != 1:
            raise RuntimeError(
                f"targeted research for {target_field.value} used "
                f"{len(submission.searches)} searches"
            )
        return submission

    def _submission(self, document: dict[str, Any]) -> AgentSubmission:
        package = _resolve_reference_package(document, self.browser)
        return AgentSubmission(
            package_json=package.model_dump_json(),
            pages=self.browser.drain_pages(),
            searches=self.browser.drain_searches(),
        )


class LiveSemanticVerifier:
    def __init__(
        self,
        *,
        model: str,
        env: dict[str, str],
        usage: UsageLog,
        source_policy: SourceQualityPolicy,
    ) -> None:
        self.model = model
        self.env = env
        self.usage = usage
        self.source_policy = source_policy

    async def verify(
        self,
        request: ResearchRequest,
        package: CompanyResearchPackage,
        *,
        fields: list[FieldName],
    ) -> VerificationReport:
        by_field = package.by_field()
        packets = [
            {
                **by_field[field].model_dump(mode="json"),
                "source_quality": self.source_policy.assess(by_field[field]),
            }
            for field in fields
        ]
        prompt = f"""
Verify each field independently using only the submitted claim, canonical
selected blocks, URLs, titles, and source-quality assessment in its field
packet. The deterministic gate resolved those blocks from an immutable browser
snapshot. Do not assume or supply facts from the rest of a page.

Return verified only when the selected blocks explicitly support the field
relationship and the complete claim. Return conflicting when submitted
eligible blocks explicitly assert incompatible values for the same field.
A claim that is not supported by its evidence is insufficient, not conflicting.
Discovery-only or unknown evidence cannot support a verdict or create a
conflict. Otherwise return insufficient.
If source_quality.mechanically_admissible is false, return insufficient without
relaxing or debating the missing source requirement. Then apply the semantic
suitability rule to the eligible submitted passages.
Set next_action using these rules:
- verified -> none
- conflicting -> human_review
- insufficient -> repair_claim when eligible evidence supports a useful,
  strictly narrower claim that can be made only by deleting words from the
  submitted claim
- insufficient -> search_evidence when the claim is well scoped but evidence
  or an appropriate official source is missing
- insufficient -> human_review only when neither automated action is safe
Give exactly one verdict for every supplied field.

{FIELD_RULES}

Source-quality contract:
{self.source_policy.prompt_text()}

Company: {request.company_name}

Field packets:
{json.dumps(packets, indent=2)}
""".strip()
        document = await _structured_query(
            prompt=prompt,
            options=_options(
                model=self.model,
                env=self.env,
                schema=VerificationReport.model_json_schema(),
                system_prompt=(
                    "You are a strict evidence verifier. The selected blocks "
                    "are your entire evidence boundary. You cannot search, read "
                    "full pages, or supply replacement evidence."
                ),
                max_turns=4,
            ),
            phase="semantic_verification:" + ",".join(field.value for field in fields),
            model=self.model,
            usage=self.usage,
        )
        return VerificationReport.model_validate(document)


class LiveClaimRepairer:
    def __init__(
        self,
        *,
        model: str,
        env: dict[str, str],
        usage: UsageLog,
        source_policy: SourceQualityPolicy,
    ) -> None:
        self.model = model
        self.env = env
        self.usage = usage
        self.source_policy = source_policy

    async def repair(
        self,
        request: ResearchRequest,
        package: CompanyResearchPackage,
        verdict: FieldVerdict,
    ) -> ClaimRepairProposal:
        field = package.by_field()[verdict.field]
        packet = {
            **field.model_dump(mode="json"),
            "source_quality": self.source_policy.assess(field),
            "verifier_reason": verdict.reason,
        }
        prompt = f"""
Narrow one partly supported claim using only its submitted eligible evidence.
The repaired claim must be made only by deleting words from the original claim
while keeping the remaining words in the same order. Do not paraphrase, add
facts, browse, or change evidence. Return repaired_claim as null when no useful,
complete deletion-only claim is explicitly supported. Copy field and
original_claim exactly from the field packet.

{FIELD_RULES}

Source-quality contract:
{self.source_policy.prompt_text()}

Company: {request.company_name}

Field packet:
{json.dumps(packet, indent=2)}
""".strip()
        document = await _structured_query(
            prompt=prompt,
            options=_options(
                model=self.model,
                env=self.env,
                schema=ClaimRepairProposal.model_json_schema(),
                system_prompt=(
                    "You are a conservative claim editor. You can only delete "
                    "words from the submitted claim and have no tools."
                ),
                max_turns=4,
            ),
            phase=f"claim_repair:{verdict.field.value}",
            model=self.model,
            usage=self.usage,
        )
        return ClaimRepairProposal.model_validate(document)


class BlindedReviewer:
    def __init__(
        self,
        *,
        model: str,
        env: dict[str, str],
        usage: UsageLog,
        source_policy: SourceQualityPolicy,
    ) -> None:
        self.model = model
        self.env = env
        self.usage = usage
        self.source_policy = source_policy

    async def review(self, candidates: list[dict[str, Any]]) -> BlindedReviewReport:
        prompt = f"""
Independently review two anonymized company records. You do not know which
workflow produced either record. Assess every field only against its cited
canonical selected blocks. The canonical_block_match flag confirms whether
each block came from the identified snapshot; no other page content is
evidence.

Labels:
- supported: admissible captured evidence explicitly supports the complete claim.
- unsupported: a selected block is invalid or does not establish the relationship.
- conflicting: two admissible captured blocks explicitly assert incompatible values.
- unresolved: the supplied captured evidence cannot determine support.
Label a field unsupported whenever source_quality.mechanically_admissible is false.
Discovery-only or unknown evidence cannot support a claim or create a conflict.

{FIELD_RULES}

Source-quality contract:
{self.source_policy.prompt_text()}

Anonymized candidates:
{json.dumps(candidates, indent=2)}
""".strip()
        document = await _structured_query(
            prompt=prompt,
            options=_options(
                model=self.model,
                env=self.env,
                schema=BlindedReviewReport.model_json_schema(),
                system_prompt=(
                    "You are an independent field-level reviewer. The submitted "
                    "canonical blocks are your entire evidence boundary."
                ),
                max_turns=8,
            ),
            phase="blinded_review",
            model=self.model,
            usage=self.usage,
        )
        return BlindedReviewReport.model_validate(document)


def _review_packet(
    candidate_id: str,
    package: CompanyResearchPackage,
    browser: AgentCoreBrowserCapture,
    source_policy: SourceQualityPolicy,
) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for item in package.fields:
        evidence = []
        for source in item.evidence:
            page = (
                None
                if source.page_id is None
                else browser.page_by_id(source.page_id)
            )
            canonical_blocks = (
                {}
                if page is None
                else {
                    block["block_id"]: block["text"]
                    for block in page.blocks
                }
            )
            evidence.append(
                {
                    **source.model_dump(mode="json"),
                    "captured_sha256": None if page is None else page.sha256,
                    "canonical_block_match": (
                        page is not None
                        and page.url == source.url
                        and bool(source.block_ids)
                        and all(
                            canonical_blocks.get(block_id) == source.passage
                            for block_id in source.block_ids
                        )
                    ),
                }
            )
        fields.append(
            {
                "field": item.field.value,
                "claim": item.claim,
                "evidence": evidence,
                "source_quality": source_policy.assess(item),
            }
        )
    return {"candidate_id": candidate_id, "fields": fields}


def _review_by_path(
    report: BlindedReviewReport,
    mapping: dict[str, str],
) -> dict[str, CandidateReview]:
    return {mapping[item.candidate_id]: item for item in report.reviews}


def _field_table(
    baseline: CompanyResearchPackage,
    outer: CompanyResearchPackage,
    outer_verification: VerificationReport | None,
    reviews: dict[str, CandidateReview],
) -> list[dict[str, Any]]:
    baseline_fields = baseline.by_field()
    outer_fields = outer.by_field()
    verification = {} if outer_verification is None else outer_verification.by_field()
    review_fields = {
        path: item_by_field.verdicts
        for path, item_by_field in reviews.items()
    }
    review_lookup = {
        path: {item.field: item for item in verdicts}
        for path, verdicts in review_fields.items()
    }
    rows = []
    for field in REQUIRED_FIELDS:
        native_review = review_lookup["native"][field]
        outer_review = review_lookup["outer"][field]
        outer_verdict = verification.get(field)
        rows.append(
            {
                "field": field.value,
                "initial_claim": baseline_fields[field].claim,
                "outer_claim": outer_fields[field].claim,
                "claim_changed": (
                    baseline_fields[field].claim != outer_fields[field].claim
                    or baseline_fields[field].evidence != outer_fields[field].evidence
                ),
                "native_review": native_review.model_dump(mode="json"),
                "outer_review": outer_review.model_dump(mode="json"),
                "outer_verifier": (
                    None if outer_verdict is None else outer_verdict.model_dump(mode="json")
                ),
            }
        )
    return rows


def _has_quality_failure(review: CandidateReview) -> bool:
    return any(item.label is not ReviewLabel.SUPPORTED for item in review.verdicts)


def _write_artifacts(
    output_root: Path,
    run_id: str,
    registration: dict[str, Any],
    result: dict[str, Any],
    pages_by_path: dict[str, list[PageArtifact]],
) -> Path:
    run_dir = output_root / run_id
    pages_dir = run_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=False)
    registration_text = json.dumps(registration, indent=2, sort_keys=True)
    (run_dir / "registration.json").write_text(registration_text + "\n")
    manifests = []
    for path, pages in pages_by_path.items():
        path_dir = pages_dir / path
        path_dir.mkdir()
        for index, page in enumerate(pages, start=1):
            filename = f"{index:02d}-{page.sha256[:12]}.json"
            (path_dir / filename).write_text(
                json.dumps(page.to_dict(), indent=2, sort_keys=True) + "\n"
            )
            manifests.append(
                {
                    "path": path,
                    "artifact": f"pages/{path}/{filename}",
                    "url": page.url,
                    "retrieved_at": page.retrieved_at,
                    "sha256": page.sha256,
                    "characters": len(page.text),
                }
            )
    result["page_manifest"] = manifests
    result["registration_sha256"] = hashlib.sha256(
        registration_text.encode("utf-8")
    ).hexdigest()
    (run_dir / "run.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return run_dir


async def run_experiment(
    registration: dict[str, Any],
    *,
    profile: str,
    region: str,
    initial_model: str,
    verifier_model: str,
    output_root: Path,
) -> tuple[Path, dict[str, Any]]:
    started_at = datetime.now(UTC).isoformat()
    experiment_id = registration["experiment"]["id"]
    registered_skill_hash = registration["research_skill"]["sha256"]
    actual_skill_hash = _native_skill_sha256()
    if actual_skill_hash != registered_skill_hash:
        raise RuntimeError(
            "company-research skill changed after registration: "
            f"registered={registered_skill_hash}, actual={actual_skill_hash}"
        )
    _validate_implementation_hashes(registration)
    run_id = experiment_id + "-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id += "-" + uuid.uuid4().hex[:8]
    env = _bedrock_env(profile, region)
    os.environ.update(env)
    usage = UsageLog()
    request = ResearchRequest.model_validate(registration["research_request"])
    limits = registration["emergency_limits"]
    source_policy = SourceQualityPolicy.from_dict(
        registration["source_quality_policy"]
    )

    async with AgentCoreBrowserCapture(
        region=region,
        allowed_domains=request.allowed_domains,
        max_searches=int(limits["max_total_searches"]),
        max_page_reads=int(limits["max_page_reads"]),
        max_results_per_search=int(limits["max_results_per_search"]),
    ) as browser:
        browser_session_id = browser.session_id
        researcher = LiveResearcher(
            browser=browser,
            initial_model=initial_model,
            recovery_model=verifier_model,
            env=env,
            usage=usage,
            source_policy=source_policy,
            initial_max_turns=int(limits["initial_max_turns"]),
            run_label="shared",
        )

        initial_submission = await researcher.research(
            request, max_passes=int(limits["max_initial_searches"])
        )
        try:
            initial_package = CompanyResearchPackage.model_validate_json(
                initial_submission.package_json
            )
            native_released = True
            native_reason = (
                "frozen initial candidate passed the common reference-interface "
                "and five-field schema checks"
            )
        except ValidationError as error:
            native_released = False
            native_reason = str(error)
            raise RuntimeError("shared initial candidate was not schema-valid") from error

        initial_pages = browser.artifacts()
        initial_operations = browser.operations()
        verifier = LiveSemanticVerifier(
            model=verifier_model,
            env=env,
            usage=usage,
            source_policy=source_policy,
        )
        claim_repairer = LiveClaimRepairer(
            model=verifier_model,
            env=env,
            usage=usage,
            source_policy=source_policy,
        )

        workflow = VerifiedResearchLoop(
            researcher,
            verifier,
            claim_repairer,
            max_research_passes=3,
            max_schema_repairs=0,
        )
        outer_result = await workflow.run_from_submission(
            request,
            initial_submission,
        )
        outer_package = outer_result.package or initial_package
        all_pages = browser.artifacts()
        all_operations = browser.operations()
        recovery_pages = all_pages[len(initial_pages) :]
        recovery_operations = all_operations[len(initial_operations) :]

    labels = ["candidate_A", "candidate_B"]
    random.Random(run_id).shuffle(labels)
    mapping = {labels[0]: "native", labels[1]: "outer"}
    packages = {"native": initial_package, "outer": outer_package}
    packets = [
        _review_packet(
            candidate_id,
            packages[path],
            browser,
            source_policy,
        )
        for candidate_id, path in mapping.items()
    ]
    reviewer = BlindedReviewer(
        model=verifier_model,
        env=env,
        usage=usage,
        source_policy=source_policy,
    )
    blinded_review = await reviewer.review(packets)
    path_reviews = _review_by_path(blinded_review, mapping)
    fields = _field_table(
        initial_package,
        outer_package,
        outer_result.verification,
        path_reviews,
    )
    outer_released = outer_result.status is RunStatus.ACCEPTED
    result = {
        "experiment": registration["experiment"],
        "case_study_notice": (
            "One preregistered initial candidate is frozen and forked into "
            "native release and outer quality-loop paths. This isolates the "
            "post-research acceptance and recovery logic; it is not a model "
            "benchmark."
        ),
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "configuration": {
            "profile": profile,
            "region": region,
            "initial_model": initial_model,
            "verifier_recovery_reviewer_model": verifier_model,
            "browser": "aws.browser.v1",
            "browser_session_id": browser_session_id,
            "initial_research_skill": NATIVE_RESEARCH_SKILL,
            "initial_research_skill_sha256": actual_skill_hash,
            "shared_frozen_initial_candidate": True,
            "initial_research_contract": False,
            "outer_contract_applied_after_freeze": True,
            "claim_repair_policy": "one deletion-only repair per field",
            "verification_evidence_boundary": "canonical_selected_blocks_only",
        },
        "submissions": {
            "shared_initial": initial_submission.model_dump(mode="json"),
        },
        "paths": {
            "native": {
                "released": native_released,
                "release_reason": native_reason,
                "package": initial_package.model_dump(mode="json"),
            },
            "outer": outer_result.model_dump(mode="json"),
        },
        "blinded_review": {
            "report": blinded_review.model_dump(mode="json"),
            "candidate_mapping": mapping,
        },
        "primary_result": {
            "native_released": native_released,
            "native_released_quality_failure": (
                native_released and _has_quality_failure(path_reviews["native"])
            ),
            "outer_released": outer_released,
            "outer_released_quality_failure": (
                outer_released and _has_quality_failure(path_reviews["outer"])
            ),
        },
        "field_table": fields,
        "browser_operations": {
            "shared_initial": [
                item.to_dict() for item in initial_operations
            ],
            "outer_recovery": [
                item.to_dict() for item in recovery_operations
            ],
        },
        "usage": usage.snapshot(),
    }
    run_dir = _write_artifacts(
        output_root,
        run_id,
        registration,
        result,
        {
            "shared_initial": initial_pages,
            "outer_recovery": recovery_pages,
        },
    )
    return run_dir, result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the preregistered live paired company-research case study."
    )
    parser.add_argument("registration", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("results/live"))
    parser.add_argument("--profile", default="das-aws")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument(
        "--initial-model", default="global.anthropic.claude-opus-5"
    )
    parser.add_argument(
        "--verifier-model", default="global.anthropic.claude-sonnet-5"
    )
    args = parser.parse_args()
    registration = json.loads(args.registration.read_text())
    try:
        run_dir, result = asyncio.run(
            run_experiment(
                registration,
                profile=args.profile,
                region=args.region,
                initial_model=args.initial_model,
                verifier_model=args.verifier_model,
                output_root=args.output_root,
            )
        )
    except Exception as error:
        print(f"Experiment failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"run_dir": str(run_dir), **result["primary_result"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
