# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""AgentCore Runtime entrypoint for the Claims multi-agent system.

Deployed via: agentcore configure --entrypoint agentcore_entrypoint.py && agentcore launch
"""
from bedrock_agentcore import BedrockAgentCoreApp

from claims_agents import ClaimData, ClaimsAssistant, create_test_claims, node_text

app = BedrockAgentCoreApp()
assistant = ClaimsAssistant()


@app.entrypoint
def invoke(payload, context):
    """Process a claim and return per-node analyses.

    Payload shapes supported:
      {"claim_id": "claim_001"}           # run a named sample claim
      {"claim": {...ClaimData fields...}} # run an ad-hoc claim
      {"prompt": "..."}                   # runs the first sample claim (smoke test)
    """
    claim = None
    if "claim" in payload:
        claim = ClaimData(**payload["claim"])
    elif "claim_id" in payload:
        claim = next(
            (c for c in create_test_claims() if c.claim_id == payload["claim_id"]),
            None,
        )
    if claim is None:
        claim = create_test_claims()[0]

    result = assistant.analyze_claim(claim)
    return {
        "claim_id": claim.claim_id,
        "status": str(result.status),
        "nodes": {nid: node_text(nr) for nid, nr in result.results.items()},
    }


if __name__ == "__main__":
    app.run()
