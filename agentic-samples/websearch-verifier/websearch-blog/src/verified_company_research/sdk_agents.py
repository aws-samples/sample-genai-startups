from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from .contracts import (
    AgentSubmission,
    CompanyResearchPackage,
    FieldName,
    ResearchRequest,
    RetrievedPage,
    VerificationReport,
)


class BrowserCapture(Protocol):
    """Application wrapper around the configured browser MCP tools."""

    def drain_pages(self) -> list[RetrievedPage]: ...

    def drain_searches(self) -> list[str]: ...


async def structured_query(prompt: str, options: Any) -> dict[str, Any]:
    """Run one isolated SDK task and return its structured output."""

    from claude_agent_sdk import ResultMessage, query

    result: ResultMessage | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            result = message

    if result is None:
        raise RuntimeError("Claude Agent SDK returned no ResultMessage")
    if result.is_error:
        raise RuntimeError(
            "; ".join(result.errors or [])
            or str(result.result)
            or result.subtype
        )
    if not isinstance(result.structured_output, dict):
        raise RuntimeError("Claude Agent SDK returned no structured output")
    return result.structured_output


class ClaudeResearcher:
    """Claude Agent SDK adapter for initial, repair, and gap research."""

    def __init__(
        self,
        *,
        research_options: Any,
        repair_options: Any,
        gap_options: Any,
        browser_capture: BrowserCapture,
    ) -> None:
        self.research_options = research_options
        self.repair_options = repair_options
        self.gap_options = gap_options
        self.browser_capture = browser_capture

    async def research(
        self,
        request: ResearchRequest,
        *,
        max_passes: int,
    ) -> AgentSubmission:
        prompt = f"""
Research {request.company_name} for the five fields in the output schema.
Use at most {max_passes} focused research passes. Browse only when a field
needs evidence. Give every field its own source metadata and shortest exact
supporting passage. Submit early when all five fields have evidence.

Request:
{request.model_dump_json(indent=2)}
""".strip()
        document = await structured_query(prompt, self.research_options)
        return self._submission(document)

    async def repair_package(
        self,
        request: ResearchRequest,
        submission: AgentSubmission,
        issues: list[str],
    ) -> AgentSubmission:
        prompt = f"""
Correct only the JSON or evidence-packaging errors listed below. Do not browse,
add claims, or change a factual value. Return the complete package.

Errors:
{json.dumps(issues, indent=2)}

Package:
{submission.package_json}
""".strip()
        document = await structured_query(prompt, self.repair_options)
        return AgentSubmission(
            package_json=json.dumps(document),
            pages=[],
            searches=[],
        )

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
        prompt = f"""
Run exactly one targeted web search to verify {target_field.value} for
{request.company_name}. Review each returned page against every unresolved
field before deciding whether another field still needs its own search.
Do not change fields that are already verified. Return the complete package,
including unchanged fields. If the search finds no support, preserve the
existing field instead of inventing evidence.

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
{package.model_dump_json(indent=2)}
""".strip()
        document = await structured_query(prompt, self.gap_options)
        return self._submission(document)

    def _submission(self, document: dict[str, Any]) -> AgentSubmission:
        return AgentSubmission(
            package_json=json.dumps(document),
            pages=self.browser_capture.drain_pages(),
            searches=self.browser_capture.drain_searches(),
        )


class ClaudeSemanticVerifier:
    """Fresh-context SDK adapter that can only reopen cited pages."""

    def __init__(self, options_for_schema: Callable[[dict[str, Any]], Any]):
        self.options_for_schema = options_for_schema

    async def verify(
        self,
        request: ResearchRequest,
        package: CompanyResearchPackage,
        *,
        fields: list[FieldName],
    ) -> VerificationReport:
        selected = package.by_field()
        packets = [
            selected[field].model_dump(mode="json")
            for field in fields
        ]
        prompt = f"""
Verify each field independently. You receive only company identity, claim,
source metadata, and cited passages. You may reopen cited URLs, but you must
not search for replacement evidence.

Return verified only when a cited passage explicitly states both the claimed
value and its relationship to the field. Do not infer headquarters from an
office location, a founding year from a copyright date, or product ownership
from an unrelated mention. Return conflicting when cited passages explicitly
assert incompatible values. Otherwise return insufficient. Give one verdict
for every supplied field and do not use one field to justify another.
Set next_action to none for verified, human_review for conflicting,
repair_claim when deleting unsupported words can produce a useful supported
claim, and search_evidence when the claim is well scoped but lacks support.

Company:
{request.company_name}

Field packets:
{json.dumps(packets, indent=2)}
""".strip()
        document = await structured_query(
            prompt,
            self.options_for_schema(VerificationReport.model_json_schema()),
        )
        return VerificationReport.model_validate(document)


def package_output_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "schema": CompanyResearchPackage.model_json_schema(),
    }
