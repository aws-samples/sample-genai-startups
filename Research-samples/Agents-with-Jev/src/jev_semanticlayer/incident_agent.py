from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter

from strands import Agent, tool

from jev_semanticlayer.config import Settings
from jev_semanticlayer.cost import calculate_usage
from jev_semanticlayer.frontier import StrandsFrontierRunner
from jev_semanticlayer.schema import Usage
from jev_semanticlayer.store import StateStore


INCIDENT_AGENT_PROMPT = """
You are an incident-response assistant operating from shared semantic state.

Always call get_incident_state before answering an incident question. Use the
timeline and evidence tools when the user asks what changed, why a conclusion
was reached, or what remains uncertain.

Treat candidate hypotheses as unconfirmed. Never describe a pending-review
claim as current fact. State confidence and uncertainty plainly. Cite evidence
IDs in the answer so an engineer can inspect the source.

Prefer a concise operational answer:
1. current status;
2. confirmed cause or current hypothesis;
3. relevant deployment;
4. pending review items;
5. the next useful investigation step supported by the available evidence.
""".strip()


@dataclass(frozen=True)
class AgentAnswer:
    text: str
    usage: Usage
    latency_ms: float


class IncidentAgent:
    def __init__(self, settings: Settings, store: StateStore) -> None:
        self.settings = settings
        self.store = store

    def _tools(self) -> list:
        store = self.store

        @tool
        def get_incident_state(service: str) -> dict:
            """Return the current resolved incident state for a service.

            Args:
                service: Canonical service name, for example checkout-api.
            """
            return store.get_current_state(service).model_dump(mode="json")

        @tool
        def get_incident_timeline(service: str) -> list[dict]:
            """Return semantic claims for a service in chronological order.

            Args:
                service: Canonical service name, for example checkout-api.
            """
            return [
                claim.model_dump(mode="json", exclude={"diagnostics"})
                for claim in store.list_claims(service)
            ]

        @tool
        def get_incident_evidence(
            service: str,
            evidence_id: str,
        ) -> dict:
            """Return the original evidence behind a semantic claim.

            Args:
                service: Canonical service name.
                evidence_id: Evidence identifier returned by the state or timeline.
            """
            evidence = store.get_evidence(service, evidence_id)
            return evidence or {
                "error": f"Evidence {evidence_id!r} was not found."
            }

        return [
            get_incident_state,
            get_incident_timeline,
            get_incident_evidence,
        ]

    def ask(self, question: str, service: str) -> AgentAnswer:
        model = StrandsFrontierRunner(self.settings).chat_model()
        agent = Agent(
            model=model,
            tools=self._tools(),
            system_prompt=INCIDENT_AGENT_PROMPT,
            callback_handler=None,
        )
        started = perf_counter()
        result = agent(
            json.dumps(
                {
                    "service": service,
                    "question": question,
                },
                sort_keys=True,
            )
        )
        elapsed_ms = (perf_counter() - started) * 1000
        tokens = result.metrics.accumulated_usage
        usage = calculate_usage(
            self.settings,
            frontier_input_tokens=int(tokens.get("inputTokens", 0)),
            frontier_output_tokens=int(tokens.get("outputTokens", 0)),
        )
        return AgentAnswer(
            text=str(result).strip(),
            usage=usage,
            latency_ms=elapsed_ms,
        )
