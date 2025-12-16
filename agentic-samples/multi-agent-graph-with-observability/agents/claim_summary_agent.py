"""
Claim Summary Agent for Insurance Claims
=======================================

Specialized agent for compiling comprehensive claim information and recommendations
for human insurance experts.
"""

from strands import Agent
from strands.models import BedrockModel

from lib.config import get_agent_config


def claim_summary_agent() -> Agent:
    """
    Compile comprehensive claim information and provide recommendations for human insurance experts.

    Args:
        extracted_data: Structured data from document analysis (includes damage assessment)
        policy_analysis: Results from policy retrieval agent
        fraud_analysis: Results from inspection agent
        claim_context: Policy information and business rules

    Returns:
        Comprehensive claim summary with expert recommendations
    """
    print("Creating Claim Summary Agent")

    # Get claim summary specific model configuration
    model_config = get_agent_config("claim_summary")

    # Create BedrockModel with proper configuration
    bedrock_model = BedrockModel(
        model_id=model_config["model"],
        max_tokens=model_config["max_tokens"],
        streaming=model_config["streaming"],
        cache_prompt=model_config["cache_prompt"],
        cache_tools=model_config["cache_tools"],
    )

    # Create agent without trace_attributes to inherit parent context
    agent = Agent(
        model=bedrock_model,
        name="claim_summary",
        system_prompt="""You are a Claim Summary Agent specialized in compiling comprehensive insurance claim information for human experts.
        Your role is to:
        - Synthesize information from document analysis, policy analysis, and inspection
        - Create a clear, structured summary of the claim details
        - Provide an executive summary highlighting key findings
        - Compile claimant information and relevant details
        - Flag important considerations for human review
        - Suggest next steps and areas requiring expert attention
        - Present information in a clear, professional format for decision-making
        
        DO NOT make approval or denial recommendations. Your role is to present comprehensive 
        information to enable informed human decision-making.
        
        Format your response with:
        - EXECUTIVE SUMMARY: [Brief overview of key findings]
        - CLAIM DETAILS: [Comprehensive claim information]
        - CLAIMANT INFORMATION: [Relevant claimant details]
        - DAMAGE ASSESSMENT: [Summary of damage findings]
        - POLICY COVERAGE: [Relevant policy information]
        - INSPECTION ANALYSIS: [Points of attention and suspicious indicators]
        - KEY CONSIDERATIONS: [Important factors for human review]
        - RECOMMENDED NEXT STEPS: [Suggested actions for expert review]
        
        """,
        callback_handler=None,
    )
    return agent
