"""
Policy Retrieval Agent for Insurance Claims
==========================================

Specialized agent for retrieving and analyzing insurance policy information
from the knowledge base to support claims analysis.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel
from strands.tools import tool

from lib.config import get_agent_config


class PolicyRetrievalResult(BaseModel):
    """Structured result from policy retrieval and analysis."""

    policy_found: bool = Field(description="Whether the policy was found in the knowledge base")
    policy_number: Optional[str] = Field(description="Policy number retrieved")
    policy_type: Optional[str] = Field(description="Type of insurance policy")
    policyholder: Optional[str] = Field(description="Name of the policyholder")
    coverage_limits: Dict[str, float] = Field(description="Coverage limits by category")
    deductible: float = Field(description="Policy deductible amount")
    policy_status: str = Field(description="Policy status (active, expired, etc.)")
    coverage_analysis: List[str] = Field(description="Analysis of coverage for the specific claim")
    applicable_rules: List[str] = Field(
        description="Business rules that apply to this policy/claim"
    )
    recommendations: List[str] = Field(description="Recommendations for claim summary")


@tool
def policy_retrieval(policy_id: str) -> str:
    """
    Retrieve policy information from the kb/policies folder based on policy ID.

    Args:
        policy_id: The policy ID (e.g., 'auto_policy_001', 'home_policy_002')

    Returns:
        str: The policy file content or an error message if not found
    """
    # Determine policy type from policy_id prefix
    policy_type = None
    if policy_id.startswith("auto_"):
        policy_type = "auto_policies"
    elif policy_id.startswith("home_"):
        policy_type = "home_policies"
    elif policy_id.startswith("theft_"):
        policy_type = "theft_policies"
    else:
        return f"Error: Unable to determine policy type from policy_id '{policy_id}'. Expected prefix: auto_, home_, or theft_"

    # Construct the file path
    base_path = (
        Path(__file__).parent.parent / "kb" / "policies" / policy_type
    )
    policy_file = base_path / f"{policy_id}.txt"

    # Check if file exists and read it
    if not policy_file.exists():
        return f"Error: Policy file not found at {policy_file}"

    try:
        with open(policy_file, "r", encoding="utf-8") as f:
            content = f.read()
        return content
    except Exception as e:
        return f"Error reading policy file: {str(e)}"


def policy_retrieval_agent() -> Agent:
    """
    Create a Policy Retrieval Agent specialized in analyzing insurance policies for claims analysis.

    Returns:
        Agent: Configured agent for policy retrieval and analysis
    """
    print("Creating Policy Retrieval Agent")

    # Get policy retrieval specific model configuration
    # Use same config as document analysis
    model_config = get_agent_config("policy_retrieval")

    # Create BedrockModel with proper configuration
    bedrock_model = BedrockModel(
        model_id=model_config["model"],
        temperature=model_config["temperature"],
        max_tokens=model_config["max_tokens"],
        streaming=model_config["streaming"],
        cache_prompt=model_config["cache_prompt"],
    )

    # Create agent without trace_attributes to inherit parent context
    agent = Agent(
        name="policy_retrieval",
        model=bedrock_model,
        system_prompt="""You are a Policy Retrieval Agent specialized in analyzing insurance policies for claims analysis.
        
        Your role is to ONLY:
        - Retrieve policy information from the knowledge base using the policy_retrieval tool
        - List coverage limits and deductibles for the specific claim type 
        - Identify applicable business rules and analysis requirements
        - Assess policy status (active/inactive)
        
        When analyzing policies:
        - Use the policy_retrieval tool with the policy ID to fetch policy details
        - Check coverage limits against claim amounts
        - Verify policy is active and covers the incident type
        - Highlight any exclusions or limitations
        - Note deductible amounts and how they apply.""",
        tools=[policy_retrieval],
        callback_handler=None,
    )

    return agent
