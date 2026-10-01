from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from boto3.dynamodb.conditions import Key
from botocore.config import Config

from jev_semanticlayer.config import Settings
from jev_semanticlayer.schema import EvidenceRecord, IncidentState, StoredClaim


def _to_dynamodb(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_dynamodb(item) for item in value]
    return value


def _service_key(service: str) -> str:
    return f"SERVICE#{service.strip().lower()}"


class StateStore(Protocol):
    def ensure_table(self) -> None: ...

    def get_current_state(self, service: str) -> IncidentState: ...

    def save_current_state(self, state: IncidentState) -> None: ...

    def put_evidence(self, evidence: EvidenceRecord) -> None: ...

    def get_evidence(self, service: str, evidence_id: str) -> dict | None: ...

    def put_claim(self, claim: StoredClaim) -> None: ...

    def get_claim(self, service: str, claim_id: str) -> StoredClaim | None: ...

    def mark_claim_superseded(self, service: str, claim_id: str) -> None: ...

    def list_claims(self, service: str) -> list[StoredClaim]: ...

    def clear_service(self, service: str) -> int: ...


class DynamoDBStateStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        config = Config(
            retries={"total_max_attempts": 5, "mode": "adaptive"},
            connect_timeout=5,
            read_timeout=15,
        )
        self.resource = settings.boto_session().resource(
            "dynamodb",
            region_name=settings.aws_region,
            config=config,
        )
        self.table = self.resource.Table(settings.semantic_state_table)

    def ensure_table(self) -> None:
        try:
            self.table.load()
            return
        except self.table.meta.client.exceptions.ResourceNotFoundException:
            pass

        self.table = self.resource.create_table(
            TableName=self.settings.semantic_state_table,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            Tags=[
                {"Key": "Project", "Value": "jev-semanticlayer"},
                {"Key": "Environment", "Value": "research"},
            ],
        )
        waiter = self.table.meta.client.get_waiter("table_exists")
        waiter.wait(
            TableName=self.settings.semantic_state_table,
            WaiterConfig={"Delay": 2, "MaxAttempts": 30},
        )
        self.table.load()

    def get_current_state(self, service: str) -> IncidentState:
        response = self.table.get_item(
            Key={"pk": _service_key(service), "sk": "CURRENT#INCIDENT"}
        )
        item = response.get("Item")
        if not item:
            return IncidentState(
                service=service,
                incident_id=f"incident:{service}:active",
            )
        return IncidentState.model_validate(item["state"])

    def save_current_state(self, state: IncidentState) -> None:
        self.table.put_item(
            Item=_to_dynamodb(
                {
                    "pk": _service_key(state.service),
                    "sk": "CURRENT#INCIDENT",
                    "item_type": "current_state",
                    "state": state.model_dump(mode="json"),
                }
            )
        )

    def put_evidence(self, evidence: EvidenceRecord) -> None:
        self.table.put_item(
            Item=_to_dynamodb(
                {
                    "pk": _service_key(evidence.service),
                    "sk": (
                        f"EVIDENCE#{evidence.occurred_at}#{evidence.case_id}"
                    ),
                    "item_type": "evidence",
                    "evidence_id": evidence.case_id,
                    "evidence": evidence.model_dump(mode="json"),
                }
            )
        )

    def get_evidence(self, service: str, evidence_id: str) -> dict | None:
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(_service_key(service))
                & Key("sk").begins_with("EVIDENCE#")
            )
        )
        for item in response.get("Items", []):
            if item.get("evidence_id") == evidence_id:
                return item["evidence"]
        return None

    def put_claim(self, claim: StoredClaim) -> None:
        self.table.put_item(
            Item=_to_dynamodb(
                {
                    "pk": _service_key(claim.service),
                    "sk": f"CLAIM#{claim.occurred_at}#{claim.claim_id}",
                    "item_type": "claim",
                    "claim_id": claim.claim_id,
                    "evidence_id": claim.evidence_id,
                    "claim": claim.model_dump(mode="json"),
                }
            )
        )

    def get_claim(self, service: str, claim_id: str) -> StoredClaim | None:
        for claim in self.list_claims(service):
            if claim.claim_id == claim_id:
                return claim
        return None

    def mark_claim_superseded(self, service: str, claim_id: str) -> None:
        claim = self.get_claim(service, claim_id)
        if not claim:
            return
        self.put_claim(
            claim.model_copy(
                update={"resolution": "superseded", "applied_to_state": False}
            )
        )

    def list_claims(self, service: str) -> list[StoredClaim]:
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(_service_key(service))
                & Key("sk").begins_with("CLAIM#")
            ),
            ScanIndexForward=True,
        )
        return [
            StoredClaim.model_validate(item["claim"])
            for item in response.get("Items", [])
        ]

    def clear_service(self, service: str) -> int:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(_service_key(service)),
            ProjectionExpression="pk, sk",
        )
        items = response.get("Items", [])
        with self.table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
        return len(items)


class InMemoryStateStore:
    def __init__(self) -> None:
        self.states: dict[str, IncidentState] = {}
        self.evidence: dict[tuple[str, str], dict] = {}
        self.claims: dict[tuple[str, str], StoredClaim] = {}

    def ensure_table(self) -> None:
        return

    def get_current_state(self, service: str) -> IncidentState:
        return self.states.get(
            service,
            IncidentState(
                service=service,
                incident_id=f"incident:{service}:active",
            ),
        ).model_copy(deep=True)

    def save_current_state(self, state: IncidentState) -> None:
        self.states[state.service] = state.model_copy(deep=True)

    def put_evidence(self, evidence: EvidenceRecord) -> None:
        self.evidence[(evidence.service, evidence.case_id)] = (
            evidence.model_dump(mode="json")
        )

    def get_evidence(self, service: str, evidence_id: str) -> dict | None:
        return self.evidence.get((service, evidence_id))

    def put_claim(self, claim: StoredClaim) -> None:
        self.claims[(claim.service, claim.claim_id)] = claim.model_copy(deep=True)

    def get_claim(self, service: str, claim_id: str) -> StoredClaim | None:
        claim = self.claims.get((service, claim_id))
        return claim.model_copy(deep=True) if claim else None

    def mark_claim_superseded(self, service: str, claim_id: str) -> None:
        claim = self.get_claim(service, claim_id)
        if claim:
            self.put_claim(
                claim.model_copy(
                    update={
                        "resolution": "superseded",
                        "applied_to_state": False,
                    }
                )
            )

    def list_claims(self, service: str) -> list[StoredClaim]:
        return sorted(
            (
                claim.model_copy(deep=True)
                for (claim_service, _), claim in self.claims.items()
                if claim_service == service
            ),
            key=lambda claim: (claim.occurred_at, claim.claim_id),
        )

    def clear_service(self, service: str) -> int:
        evidence_keys = [
            key for key in self.evidence if key[0] == service
        ]
        claim_keys = [key for key in self.claims if key[0] == service]
        for key in evidence_keys:
            del self.evidence[key]
        for key in claim_keys:
            del self.claims[key]
        removed_state = int(service in self.states)
        self.states.pop(service, None)
        return len(evidence_keys) + len(claim_keys) + removed_state
