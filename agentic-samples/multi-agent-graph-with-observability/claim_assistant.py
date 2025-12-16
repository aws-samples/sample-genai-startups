"""
Multi-Agent Sample using Strands Agents Graph
=========================================================================

This system implements an intelligent insurance claims analysis workflow to
prepare for a human agent review with four specialized agents:
1. Document Analysis Agent - Analyzes claim data and supporting evidence
2. Policy Retrieval Agent - Retrieves and analyzes insurance policy info
3. Inspection Agent - Identifies suspicious claims
4. Claim Summary Agent - Compiles comprehensive information for human experts

The agents are orchestrated using a Strands Agents Graph for deterministic
execution flow, providing comprehensive analysis for human decision-making.
"""

import os
import re
import traceback
from typing import List

from opentelemetry import baggage, context
from strands.multiagent import GraphBuilder
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.multiagent.graph import GraphState
from strands.types.content import ContentBlock

from agents.claim_summary_agent import claim_summary_agent
from agents.document_analysis_agent import (
    DocumentAnalysisResult,
    document_analysis_agent,
)
from agents.inspection_agent import inspection_agent
from agents.policy_retrieval_agent import policy_retrieval_agent
from lib.config import get_config
from lib.data_models import ClaimData, ProcessingResult


class ClaimsAssistant:
    """Main insurance claims analysis system using Graph-based orchestration for human expert support"""

    def __init__(self):
        """Initialize the claims processor with specialized agents in a Graph"""
        # Load configuration
        self.config = get_config()

        # Build the analysis graph
        self.graph = self._build_analysis_graph()

    def _all_dependencies_complete(self, required_nodes: list[str]):
        """Factory function to create AND condition for multiple dependencies."""

        def check_all_complete(state: GraphState) -> bool:
            return all(
                node_id in state.results and state.results[node_id].status == Status.COMPLETED
                for node_id in required_nodes
            )

        return check_all_complete

    def _document_analysis_valid(self, state: GraphState) -> bool:
        """Check if document analysis completed successfully with valid status."""
        doc_analysis_result = state.results.get("document_analysis")
        if not doc_analysis_result or not doc_analysis_result.result:
            return False

        # Access the structured_output from the AgentResult
        structured_result = doc_analysis_result.result.structured_output
        if structured_result and hasattr(structured_result, "status"):
            return structured_result.status == "valid"

        return False

    def _build_analysis_graph(self):
        """Build the insurance claims analysis graph with conditional routing"""
        builder = GraphBuilder()

        # Add nodes for each specialized agent
        builder.add_node(document_analysis_agent(), "document_analysis")
        builder.add_node(policy_retrieval_agent(), "policy_retrieval")
        builder.add_node(inspection_agent(), "inspection")
        builder.add_node(claim_summary_agent(), "claim_summary")

        # Define conditional dependencies (edges)
        # Document analysis is the entry point
        # Only proceed to other agents if document analysis is valid
        builder.add_edge(
            "document_analysis", "policy_retrieval", condition=self._document_analysis_valid
        )
        builder.add_edge("document_analysis", "inspection", condition=self._document_analysis_valid)

        # Claim summary depends on all other agents AND valid document analysis
        builder.add_edge(
            "policy_retrieval",
            "claim_summary",
            condition=self._all_dependencies_complete(
                ["document_analysis", "policy_retrieval", "inspection"]
            ),
        )
        builder.add_edge(
            "inspection",
            "claim_summary",
            condition=self._all_dependencies_complete(
                ["document_analysis", "policy_retrieval", "inspection"]
            ),
        )

        # Set entry point
        builder.set_entry_point("document_analysis")

        # Configure execution limits for safety
        builder.set_execution_timeout(900)  # 15 minute timeout
        builder.set_node_timeout(300)  # 5 minute per node timeout

        return builder.build()

    def prepare_claim_context(self, claim_data: ClaimData) -> str:
        """Prepare comprehensive context for claim summary"""

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

    def prepare_multimodal_content(self, claim_data: ClaimData) -> List[ContentBlock]:
        """Prepare multimodal content blocks for analysis"""
        content_blocks = []

        # Add claim description if provided
        if claim_data.description:
            content_blocks.append({"text": f"Claim Description: {claim_data.description}"})

        # Add instruction text
        content_blocks.append(
            {
                "text": "Please analyze the following files and extract structured information for insurance claim summary:"
            }
        )

        # Process each file
        photos_count = 0
        docs_count = 0

        for file_path in claim_data.documents:
            if not os.path.exists(file_path):
                print(f"WARNING: File not found: {file_path}")
                continue

            file_ext = os.path.splitext(file_path)[1].lower()

            # Handle image files
            if file_ext in [".png", ".jpg", ".jpeg"]:
                with open(file_path, "rb") as f:
                    image_bytes = f.read()

                content_blocks.append(
                    {
                        "image": {
                            "format": file_ext[1:],  # Remove the dot
                            "source": {"bytes": image_bytes},
                        }
                    }
                )
                photos_count += 1

            # Handle document files
            elif file_ext in [".pdf", ".txt"]:
                if file_ext == ".txt":
                    with open(file_path, "r", encoding="utf-8") as f:
                        doc_content = f.read()
                    content_blocks.append(
                        {
                            "text": f"Document content from {os.path.basename(file_path)}:\n{doc_content}"
                        }
                    )
                else:  # PDF
                    with open(file_path, "rb") as f:
                        pdf_bytes = f.read()
                    content_blocks.append(
                        {
                            "document": {
                                "format": "pdf",
                                "name": os.path.basename(file_path),
                                "source": {"bytes": pdf_bytes},
                            }
                        }
                    )
                docs_count += 1
            else:
                print(f"WARNING: Unsupported file type: {file_ext}")

        # Only instruction text
        if not content_blocks or len(content_blocks) <= 2:
            raise ValueError("No valid files provided for analysis")

        return content_blocks

    def analyze_claim(self, claim_data: ClaimData, debug_mode: bool = False) -> ProcessingResult:
        """Analyze a single insurance claim through the multi-agent graph"""
        print(f"Starting analysis for claim {claim_data.claim_id}")

        # Validate that evidence documents are provided
        if not claim_data.documents:
            raise ValueError("Evidence documents are required for claim summary")

        # Prepare comprehensive claim context
        claim_context = self.prepare_claim_context(claim_data)

        # Add analysis instructions to the context
        enhanced_context = f"""
        You are an insurance claims assistant for human agents.
        You coordinate specialized agents in a graph to analyze insurance \
        claims and provide a comprehensive analysis of the information on the claim \
            and the applicable policies to human agents.
        You have access to four specialized agents:

        1. document_analysis_agent - Analyzes claim data \
            and evidence and extracts information from text and images to be analyzed by future agents
        2. policy_retrieval_agent - Retrieves and analyzes insurance \
            policy information from knowledge base
        3. inspection_agent - Analyzes claims for inconsistent information
        4. claim_summary_agent - Compiles comprehensive information about the claim and claimant policies for human review.

        IMPORTANT: Always pass the claim_id parameter to each agent call \
            for proper session tracking and tracing.
            When calling any agent, include claim_id as a parameter with the \
            current claim's ID.

        Provide a comprehensive summary of the entire claims analysis graph.

        Claim Context:
        {claim_context}

        """

        # Get multimodal content blocks
        multimodal_blocks = self.prepare_multimodal_content(claim_data)

        # Combine context and multimodal content
        content_blocks = [ContentBlock(text=enhanced_context)] + multimodal_blocks

        try:
            print("Executing multi-agent graph analysis...")
            print(f"Analyzing claim with {len(claim_data.documents)} evidence files")

            # Execute the graph with the prepared prompt
            graph_result = self.graph(content_blocks)

            print(f"Graph execution completed with status: {graph_result.status}")
            print(f"Executed {graph_result.completed_nodes}/{graph_result.total_nodes} nodes")
            print(f"Total execution time: {graph_result.execution_time}ms")

            # Debug: Print graph result structure
            if debug_mode:
                self._print_detailed_execution_logs(graph_result, debug_mode)

            return graph_result

        except Exception as e:
            print(f"ERROR: Error analyzing claim {claim_data.claim_id}: {e}")
            print(f"Full traceback: {traceback.format_exc()}")
            # Return failed result
            return ProcessingResult(
                claim_id=claim_data.claim_id,
                status="failed",
                analysis_notes=[f"Analysis failed: {str(e)}"],
            )

    def _print_detailed_execution_logs(
        self, graph_result: MultiAgentResult, debug_mode: bool = False
    ):
        """Print detailed execution logs for debugging"""
        print(f"Graph result type: {type(graph_result)}")
        print(f"Graph result attributes: {dir(graph_result)}")
        for node_id, node_result in graph_result.results.items():
            print(f"Node {node_id} result type: {type(node_result.result)}")
            if hasattr(node_result.result, "message"):
                print(f"Node {node_id} message type: {type(node_result.result.message)}")
                print(f"Node {node_id} message: {node_result.result.message}")
            break  # Just check first node to avoid spam

        # Log execution order and node results
        if hasattr(graph_result, "execution_order") and graph_result.execution_order:
            print("Execution Order:")
            for i, node in enumerate(graph_result.execution_order, 1):
                print(f"  {i}. {node.node_id}")

        # Log individual node results
        print("Node Results Summary:")
        for node_id, node_result in graph_result.results.items():
            if node_result.result:
                try:
                    # Try different ways to extract the output text
                    output_text = None

                    # Method 1: Check if it has message.content structure
                    if hasattr(node_result.result, "message"):
                        message = node_result.result.message
                        if hasattr(message, "content") and len(message.content) > 0:
                            output_text = str(message.content[0].text)
                        elif isinstance(message, dict) and "content" in message:
                            if isinstance(message["content"], list) and len(message["content"]) > 0:
                                content_item = message["content"][0]
                                if isinstance(content_item, dict) and "text" in content_item:
                                    output_text = str(content_item["text"])
                                else:
                                    output_text = str(content_item)
                            else:
                                output_text = str(message["content"])
                        else:
                            output_text = str(message)

                    # Method 2: Direct string conversion if above fails
                    if output_text is None:
                        output_text = str(node_result.result)

                    if debug_mode:
                        print(f"{node_id} FULL OUTPUT:")
                        print(f"     {output_text}")
                        print(f"     {'-' * 40}")
                    else:
                        output_preview = output_text[:200] if output_text else "No output"
                        print(f"  {node_id}: {output_preview}...")

                except Exception as e:
                    print(f"WARNING: {node_id}: Error extracting output - {str(e)}")
                    if debug_mode:
                        print(f"     Raw result type: {type(node_result.result)}")
                        print(f"     Raw result: {node_result.result}")
            else:
                print(f"WARNING: {node_id}: No result or failed")

        print("" + "=" * 50)
