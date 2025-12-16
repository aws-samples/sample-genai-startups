"""
Example: Analyzing a car insurance claim with photo evidence
"""

import os
import sys
from datetime import datetime
from uuid import uuid4 as uuid

from opentelemetry import baggage, context

# Add parent directory to path to import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from claim_assistant import ClaimsAssistant
from lib.data_models import ClaimData


def set_session_context(session_id):
    """Set the session ID in OpenTelemetry baggage for trace correlation"""
    ctx = baggage.set_baggage("session.id", session_id)
    token = context.attach(ctx)
    print(f"Session ID '{session_id}' attached to telemetry context")
    return token


def extract_claim_summary_text(result):
    """Extract the formatted claim summary text from the graph result"""
    try:
        # Check if this is a AnalysisResult first
        if hasattr(result, "claim_summary") and result.claim_summary:
            return result.claim_summary

        # Handle MultiAgentResult
        if not hasattr(result, "results") or "claim_summary" not in result.results:
            return None

        claim_summary_result = result.results["claim_summary"]
        if not claim_summary_result.result:
            return None

        # Try to extract the message content
        if not hasattr(claim_summary_result.result, "message"):
            return str(claim_summary_result.result)

        message = claim_summary_result.result.message

        # Handle different message structures
        if hasattr(message, "content") and len(message.content) > 0:
            return message.content[0].text

        if isinstance(message, dict) and "content" in message:
            if isinstance(message["content"], list) and len(message["content"]) > 0:
                content_item = message["content"][0]
                if isinstance(content_item, dict) and "text" in content_item:
                    return content_item["text"]
                return str(content_item)
            return str(message["content"])

        return str(message)

    except Exception as e:
        print(f"WARNING: Error extracting claim summary text: {e}")
        return None


def main():
    # Initialize the claims assistant
    assistant = ClaimsAssistant()

    # Create claim data with default policy and fenderbender photo
    claim_data = ClaimData(
        claim_id="CLM-2024-001",
        policy_number="auto_12345",
        claimant_name="John Doe",
        incident_date=datetime.now().strftime("%Y-%m-%d"),
        incident_type="auto",
        location="W livington st & N orange ave, Orlando, FL",
        description="Minor fender bender in parking lot",
        estimated_damage=2500.0,
        documents=["kb/photos/fenderbender1.jpeg"],
    )

    # Analyze the claim
    print("Analyzing car insurance claim...")
    context_token = ""
    try:
        # Create a uuid session ID for observability
        session_id = str(uuid())
        context_token = set_session_context(session_id)
        result = assistant.analyze_claim(claim_data)
        print("Claim analyzed successfully.")
    finally:
        context.detach(context_token)
        print("Analysis complete.")

    # Display results
    print(f"\n{'=' * 80}")
    print("ANALYSIS RESULTS")
    print(f"{'=' * 80}")

    # Check if this is a AnalysisResult (failure case) or MultiAgentResult (success case)
    if hasattr(result, "claim_summary") and result.claim_summary:
        # This is a AnalysisResult with claim summary
        print(f"{result.claim_summary}")
    else:
        # Try to extract from MultiAgentResult
        claim_summary_text = extract_claim_summary_text(result)

        if claim_summary_text:
            print(f"{claim_summary_text}")
        else:
            print("WARNING: Claim summary not available or analysis incomplete.")
            # Show overall analysis status for debugging
            print(f"Analysis Status: {result.status}")

            # Only show node info if it's a MultiAgentResult
            if hasattr(result, "completed_nodes") and hasattr(result, "total_nodes"):
                print(f"Completed Nodes: {result.completed_nodes}/{result.total_nodes}")

            if hasattr(result, "results"):
                print("\nNode Results:")
                for node_id, node_result in result.results.items():
                    status = node_result.status if hasattr(node_result, "status") else "unknown"
                    print(f"  - {node_id}: {status}")
            elif hasattr(result, "analysis_notes") and result.analysis_notes:
                print("\nAnalysis Notes:")
                for note in result.analysis_notes:
                    print(f"  - {note}")

    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
