# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Insurance claims multi-agent system.

This module packages the agents and graph built in Lab 1 so they can be
reused by Lab 2 (operational metrics) and Lab 3 (quality evaluation)
without rebuilding them from scratch.
"""
import os
from typing import List

from pydantic import BaseModel, Field
from strands import Agent
from strands.multiagent import GraphBuilder
from strands.multiagent.base import MultiAgentResult, Status
from strands.multiagent.graph import GraphState
from strands.models import BedrockModel
from strands.types.content import ContentBlock


# ---------- Data models ----------

class ClaimData(BaseModel):
    """Insurance claim data structure."""
    claim_id: str
    policy_number: str
    claimant_name: str
    incident_date: str
    incident_type: str
    description: str
    estimated_damage: float
    documents: List[str]
    location: str


class AnalyzedDocument(BaseModel):
    content: str = Field(description="Extracted text content")
    extension: str = Field(description="Document type")


class AnalyzedImages(BaseModel):
    description: str = Field(description="Image analysis")
    file_name: str = Field(description="File name")
    extension: str = Field(description="Image type")


class DocumentAnalysisResult(BaseModel):
    analyzed_documents: List[AnalyzedDocument]
    analyzed_images: List[AnalyzedImages]
    status: str
    summary: str


# ---------- Model + agent factories ----------

def get_bedrock_model() -> BedrockModel:
    return BedrockModel(
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        region_name="us-east-1",
        temperature=0.1,
    )


model = get_bedrock_model()


def document_analysis_agent() -> Agent:
    return Agent(
        name="DocumentAnalysisAgent",
        model=model,
        system_prompt="""
        You are a document analysis specialist for insurance claims.
        Analyze provided documents and images to extract relevant information.
        Set status to 'valid' if analysis is successful, 'invalid' if documents are insufficient.

        For identified_documents, list the exact filenames from the 'Supporting Evidence' field
        in the claim context. Do not infer or invent filenames not present there.

        ALWAYS end your response with a single JSON block on its own lines in this exact format:
        STRUCTURED_OUTPUT:
        {"identified_documents": ["<filename1>", ...], "status": "valid|invalid"}
        """,
    )


def policy_retrieval_agent() -> Agent:
    return Agent(
        name="PolicyRetrievalAgent",
        model=model,
        system_prompt="""
        You are a policy analysis specialist.
        Analyze insurance policies to determine coverage, deductibles, and applicable terms.
        Provide clear coverage analysis for the claim.

        ALWAYS end your response with a single JSON block on its own lines in this exact format:
        STRUCTURED_OUTPUT:
        {"coverage": true|false}
        """,
    )


def inspection_agent() -> Agent:
    return Agent(
        name="InspectionAgent",
        model=model,
        system_prompt="""
        You are an inspection specialist for insurance claims.
        Analyze claims for inconsistencies, unusual patterns, or fraud indicators.

        Risk level taxonomy (choose exactly one):
          - low:    damage <= $5,000, no theft/fire, single clear cause
          - medium: damage $5,000-$10,000, or minor inconsistencies, or contested liability
          - high:   damage > $10,000, theft, fire, multiple inconsistencies, or suspicious timeline

        Fraud flag vocabulary — use only these lowercase tags, and only when clearly indicated:
          - high_value:           damage amount exceeds $10,000
          - theft:                incident involves stolen property or forced entry
          - fire:                 incident involves fire, arson, or unexplained ignition
          - inconsistent_timeline: reported times or dates don't match
          - missing_evidence:     expected documents or reports are not provided
          - prior_claims:         claimant has a recent history of similar claims

        Omit fraud_flags entirely (empty list) when the claim is clean.

        ALWAYS end your response with a single JSON block on its own lines in this exact format:
        STRUCTURED_OUTPUT:
        {"risk_level": "low|medium|high", "fraud_flags": ["<tag1>", ...]}
        """,
    )


def claim_summary_agent() -> Agent:
    return Agent(
        name="ClaimSummaryAgent",
        model=model,
        system_prompt="""
        You are a claims summary specialist.
        Compile comprehensive analysis from all previous agents into a clear summary.
        Provide actionable insights for human insurance experts.
        Include key findings, coverage details, and recommendations.
        """,
    )


# ---------- Graph construction ----------

def _document_analysis_valid(state: GraphState) -> bool:
    node_result = state.results.get("document_analysis")
    if not node_result or node_result.status != Status.COMPLETED:
        return False
    structured = getattr(node_result.result, "structured_output", None)
    if structured is not None and hasattr(structured, "status"):
        return structured.status == "valid"
    return True


def _all_dependencies_complete(required_nodes: List[str]):
    def check(state: GraphState) -> bool:
        return all(
            nid in state.results and state.results[nid].status == Status.COMPLETED
            for nid in required_nodes
        )
    return check


def _build_graph():
    builder = GraphBuilder()
    builder.add_node(document_analysis_agent(), "document_analysis")
    builder.add_node(policy_retrieval_agent(), "policy_retrieval")
    builder.add_node(inspection_agent(), "inspection")
    builder.add_node(claim_summary_agent(), "claim_summary")

    builder.add_edge("document_analysis", "policy_retrieval", condition=_document_analysis_valid)
    builder.add_edge("document_analysis", "inspection", condition=_document_analysis_valid)

    summary_cond = _all_dependencies_complete(
        ["document_analysis", "policy_retrieval", "inspection"]
    )
    builder.add_edge("policy_retrieval", "claim_summary", condition=summary_cond)
    builder.add_edge("inspection", "claim_summary", condition=summary_cond)

    builder.set_entry_point("document_analysis")
    builder.set_execution_timeout(900)
    builder.set_node_timeout(300)
    return builder.build()


# ---------- Content preparation ----------

def prepare_multimodal_content(claim_data: ClaimData) -> List[dict]:
    blocks: List[dict] = []
    if claim_data.description:
        blocks.append({"text": f"Claim Description: {claim_data.description}"})
    blocks.append({"text": "Analyze the following files and extract structured information:"})
    for file_path in claim_data.documents:
        if not os.path.exists(file_path):
            continue
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg"):
            with open(file_path, "rb") as f:
                blocks.append({
                    "image": {"format": ext[1:], "source": {"bytes": f.read()}}
                })
    return blocks


def prepare_claim_context(claim_data: ClaimData) -> str:
    return f"""
    CLAIM INFORMATION:
    - Claim ID: {claim_data.claim_id}
    - Policy Number: {claim_data.policy_number}
    - Claimant: {claim_data.claimant_name}
    - Incident Date: {claim_data.incident_date}
    - Incident Type: {claim_data.incident_type}
    - Location: {claim_data.location}
    - Description: {claim_data.description}
    - Estimated Damage: ${claim_data.estimated_damage:,.2f}
    - Supporting Evidence: {', '.join(claim_data.documents)}
    """


# ---------- Orchestrator ----------

class ClaimsAssistant:
    """Main insurance claims analysis system."""

    def __init__(self):
        self.graph = _build_graph()

    def analyze_claim(self, claim_data: ClaimData) -> MultiAgentResult:
        context = prepare_claim_context(claim_data)
        multimodal = prepare_multimodal_content(claim_data)
        enhanced = f"""
        You are an insurance claims assistant coordinating specialized agents.
        Analyze the claim comprehensively for human expert review.

        Claim Context:
        {context}
        """
        content_blocks = [ContentBlock(text=enhanced)] + multimodal
        return self.graph(content_blocks)


# ---------- Test fixtures for Lab 2 / Lab 3 ----------

def create_test_claims() -> List[ClaimData]:
    """Return a small set of sample claims for metrics and evaluation labs."""
    return [
        ClaimData(
            claim_id="claim_001",
            policy_number="POL-AUTO-12345",
            claimant_name="John Smith",
            incident_date="2024-10-15",
            incident_type="Vehicle Collision",
            description=(
                "Claimant was stopped at a red light when another vehicle rear-ended them. "
                "Damage is limited to the rear bumper and trunk lid; the vehicle remained drivable. "
                "Other driver accepted responsibility at the scene. No injuries reported."
            ),
            estimated_damage=3500.00,
            documents=["accident_report.pdf", "damage_photos.jpg"],
            location="Main St & 5th Ave, Seattle, WA",
        ),
        ClaimData(
            claim_id="claim_002",
            policy_number="POL-HOME-67890",
            claimant_name="Jane Doe",
            incident_date="2024-11-02",
            incident_type="Water Damage",
            description=(
                "A supply line to the upstairs bathroom sink failed overnight, flooding the bathroom "
                "and causing ceiling damage in the kitchen directly below. Claimant shut off the main "
                "water valve on discovering the leak. A licensed plumber repaired the line the same day."
            ),
            estimated_damage=8200.00,
            documents=["plumber_report.pdf", "water_damage_photos.jpg"],
            location="1234 Oak Drive, Portland, OR",
        ),
        ClaimData(
            claim_id="claim_003",
            policy_number="POL-AUTO-54321",
            claimant_name="Alex Rivera",
            incident_date="2024-11-20",
            incident_type="Theft",
            description=(
                "Claimant's vehicle was parked overnight in a secured downtown garage. In the morning "
                "the driver's side window was found smashed and the aftermarket stereo, a laptop bag, "
                "and other personal items had been taken. Police were called and a report was filed."
            ),
            estimated_damage=14500.00,
            documents=["police_report.pdf", "garage_security_footage.mp4"],
            location="Downtown parking garage, Level 2",
        ),
    ]


import json as _json
import re as _re

_STRUCTURED_RE = _re.compile(
    r"STRUCTURED_OUTPUT:\s*(\{.*?\})\s*$", _re.DOTALL
)


def parse_structured_tail(text: str) -> dict:
    """Extract the trailing STRUCTURED_OUTPUT JSON block from an agent response.

    Returns an empty dict if the block is missing or malformed.
    """
    if not text:
        return {}
    match = _STRUCTURED_RE.search(text)
    if not match:
        return {}
    try:
        return _json.loads(match.group(1))
    except _json.JSONDecodeError:
        return {}


def node_text(node_result) -> str:
    """Extract the plain text response from a graph NodeResult."""
    result = getattr(node_result, "result", None)
    message = getattr(result, "message", None)
    content = getattr(message, "content", None) or (message.get("content") if isinstance(message, dict) else None)
    if not content:
        return ""
    parts = []
    for block in content:
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)
