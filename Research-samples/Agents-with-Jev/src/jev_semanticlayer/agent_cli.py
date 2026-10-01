from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import openai
from botocore.exceptions import BotoCoreError, ClientError
from typesafe_sdk import TypeSafeError

from jev_semanticlayer.config import Settings
from jev_semanticlayer.incident_agent import IncidentAgent
from jev_semanticlayer.judges import HybridJudge
from jev_semanticlayer.schema import EvidenceRecord
from jev_semanticlayer.store import DynamoDBStateStore
from jev_semanticlayer.workflow import SemanticIngestionWorkflow


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_evidence(path: Path) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(EvidenceRecord.model_validate_json(line))
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: {error}") from error
    return records


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Jev-backed shared semantic incident agent."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("setup", help="Create the DynamoDB state table.")

    ingest = subparsers.add_parser(
        "ingest", help="Compile evidence into shared semantic state."
    )
    ingest.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "incidents.jsonl",
    )

    rebuild = subparsers.add_parser(
        "rebuild",
        help="Clear one service partition and rebuild it from evidence.",
    )
    rebuild.add_argument("--service", default="checkout-api")
    rebuild.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "incidents.jsonl",
    )

    show = subparsers.add_parser(
        "show", help="Show current state and the semantic timeline."
    )
    show.add_argument("--service", default="checkout-api")
    show.add_argument(
        "--diagnostics",
        action="store_true",
        help="Include raw Jev probabilities and compiler diagnostics.",
    )

    ask = subparsers.add_parser("ask", help="Ask the incident agent.")
    ask.add_argument("question")
    ask.add_argument("--service", default="checkout-api")

    demo = subparsers.add_parser(
        "demo", help="Create the table, ingest fixtures, and ask the agent."
    )
    demo.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "incidents.jsonl",
    )
    demo.add_argument("--service", default="checkout-api")
    demo.add_argument(
        "--question",
        default=(
            "What happened, what is the current root cause, and which evidence "
            "supports that conclusion?"
        ),
    )
    return parser


def _store(settings: Settings) -> DynamoDBStateStore:
    return DynamoDBStateStore(settings)


def _ingest(
    settings: Settings,
    store: DynamoDBStateStore,
    input_path: Path,
) -> None:
    workflow = SemanticIngestionWorkflow(
        store=store,
        judge=HybridJudge(settings),
    )
    for evidence in _load_evidence(input_path):
        result = workflow.process(evidence)
        status = "skipped" if result.skipped else "processed"
        assessment = result.assessment
        print(
            json.dumps(
                {
                    "evidence_id": result.evidence_id,
                    "status": status,
                    "semantic_type": (
                        assessment.update_type.value if assessment else None
                    ),
                    "resolution": (
                        "pending_review"
                        if result.claim_id in result.state.pending_review_ids
                        else "active"
                    ),
                }
            )
        )


def main() -> int:
    args = _parser().parse_args()
    settings = Settings.from_env()
    store = _store(settings)
    try:
        if args.command == "setup":
            store.ensure_table()
            print(f"Table ready: {settings.semantic_state_table}")
            return 0

        if args.command == "ingest":
            store.ensure_table()
            _ingest(settings, store, args.input)
            return 0

        if args.command == "rebuild":
            store.ensure_table()
            removed = store.clear_service(args.service)
            print(f"Removed {removed} items for {args.service}.")
            _ingest(settings, store, args.input)
            return 0

        if args.command == "show":
            store.ensure_table()
            output = {
                "current": store.get_current_state(args.service).model_dump(
                    mode="json"
                ),
                "timeline": [
                    claim.model_dump(
                        mode="json",
                        exclude=None if args.diagnostics else {"diagnostics"},
                    )
                    for claim in store.list_claims(args.service)
                ],
            }
            print(json.dumps(output, indent=2))
            return 0

        if args.command == "ask":
            store.ensure_table()
            answer = IncidentAgent(settings, store).ask(
                args.question,
                args.service,
            )
            print(answer.text)
            print(
                json.dumps(
                    {
                        "latency_ms": answer.latency_ms,
                        "usage": answer.usage.model_dump(),
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 0

        if args.command == "demo":
            store.ensure_table()
            _ingest(settings, store, args.input)
            answer = IncidentAgent(settings, store).ask(
                args.question,
                args.service,
            )
            print("\nAgent answer\n")
            print(answer.text)
            print(
                json.dumps(
                    {
                        "latency_ms": answer.latency_ms,
                        "usage": answer.usage.model_dump(),
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 0
    except (
        BotoCoreError,
        ClientError,
        TypeSafeError,
        openai.APIError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
