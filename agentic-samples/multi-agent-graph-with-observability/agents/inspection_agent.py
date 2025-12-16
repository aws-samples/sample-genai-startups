"""
Inspection Agent for Insurance Claims
=====================================

Specialized agent for analyzing claims for suspicious patterns and points of attention.
"""

from strands import Agent
from strands.models import BedrockModel

from lib.config import get_agent_config


def inspection_agent() -> Agent:
    """
    Create an Inspection Agent specialized in identifying incoherent information

    Returns:
        Agent: Configured agent for inspection analysis
    """
    print("Creating Inspection Agent")

    # Get inspection specific model configuration
    model_config = get_agent_config("inspection")

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
        name="inspection",
        model=bedrock_model,
        system_prompt="""You are an Inspection Agent specialized in identifying inconsistent information in insurance claims.
        Your role is to: 
        - Check analysis from the Document Analysis agent to find information about photos and documents uploaded by the claimants
        - Check for inconsistencies in the claim narrative and documentation
        - Evaluate timing and circumstances of the incident 
        - Highlight specific points of attention that require human review
         
        Flag any inconsistent element for human review.
        
        Format your response with:
        - POINTS OF ATTENTION: [List specific areas requiring review]
        - INCONSISTENCIES IDENTIFIED: [Any contradictions found]
        - RECOMMENDED ACTIONS: [Specific next steps for investigation]""",
        callback_handler=None,
    )

    return agent
