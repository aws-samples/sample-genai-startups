"""
Document Analysis Agent for Insurance Claims
=============================================

Specialized agent for extracting text from claim documents and images
with structured JSON output.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from strands import Agent
from strands.agent.agent_result import AgentResult
from strands.hooks import (
    AfterInvocationEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    HookProvider,
    HookRegistry,
)
from strands.models import BedrockModel
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.types.content import ContentBlock, Message

from lib.config import get_agent_config


# Pydantic models for structured output
class AnalyzedDocument(BaseModel):
    """Text extracted from a document"""

    content: str = Field(description="Extracted text content")
    extension: str = Field(description="Type of source (text, pdf)")


class AnalyzedImages(BaseModel):
    """Data about images"""

    description: str = Field(description="Extracted text content")
    file_name: str = Field(description="File name")
    extension: str = Field(description="Type of image (png, jpg)")


class DocumentAnalysisResult(BaseModel):
    """Complete structured output from document analysis."""

    analyzed_documents: List[AnalyzedDocument] = Field(
        description="Raw text extracted from text documents or PDFs"
    )
    analyzed_images: List[AnalyzedImages] = Field(
        description="Raw description of extracted images and photos"
    )
    analysis_summary: Dict[str, int] = Field(description="Summary of analyzed items")
    status: str = Field(
        description="Analysis status: 'valid' if documents were successfully analyzed and contain relevant claim information, 'invalid' if analysis failed or documents are insufficient"
    )
    validation_notes: str = Field(
        description="Notes about the validation status and any issues found"
    )


def process_result(event: AfterToolCallEvent) -> None:
    if event.tool_use:
        print(f"Tool use event: {event.tool_use}")


def document_analysis_agent() -> Agent:
    """
    Create a Document Analysis Agent for text extraction from documents.

    Returns:
        Agent: Configured agent for extracting text from documents and images
    """
    print("Creating Document Analysis Agent")

    # Get document analysis specific model configuration
    model_config = get_agent_config("document_analysis")

    # Create BedrockModel with proper configuration
    bedrock_model = BedrockModel(
        model_id=model_config["model"],
        temperature=model_config["temperature"],
        max_tokens=model_config["max_tokens"],
        streaming=model_config["streaming"],
        cache_prompt=model_config["cache_prompt"],
        cache_tools=model_config["cache_tools"],
    )

    # Create agent without trace_attributes to inherit parent context
    agent = Agent(
        name="document_analysis",
        model=bedrock_model,
        system_prompt="""You are a Document Analysis Agent specialized in text extraction from insurance claim documents and images.

Your ONLY role is to:
- Extract text content from documents (PDF, images, scanned documents)
- Extract very detailed description of the scene from images, including information about the car, make, model, color, where the incident happened, the type of incident, the severity and the location of damages, whether the damage is water damage, fire damage, or car damage.
- Identify and extract structured information like policy numbers, dates, names, addresses
- Read text from images including license plates, VINs, and document text
- Organize extracted information into structured JSON format
- Preserve original text exactly as found in documents
- VALIDATE that the analyzed documents contain sufficient information for claim summary
   
When analyzing documents/images:
- Extract all visible text accurately
- Identify policy numbers, dates, names, and addresses
- Read license plates, VINs, and identifying information
- Organize information into the provided JSON structure
- Only include information that is explicitly visible in the source

VALIDATION REQUIREMENTS:
- Set status to 'valid' ONLY if:
  * Documents contain clear evidence of damage or incident
  * Images show identifiable damage, vehicles, or property
  * Sufficient information is available for claim summary
  * Text extraction was successful
- Set status to 'invalid' if:
  * Documents are unreadable or corrupted
  * No relevant claim information found
  * Images are unclear or don't show damage/incident
  * Analysis failed or incomplete

Always provide validation_notes explaining your decision.

Focus solely on accurate text extraction, structured data organization, and validation.""",
        callback_handler=None,
        trace_attributes=False,
        structured_output_model=DocumentAnalysisResult,
    )

    return agent
