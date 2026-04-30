import json
import uuid
from datetime import datetime


# Owner lookup mirrors the GetOwnerInfo Lambda so the booking can record
# the primary passenger without requiring the agent to pass firstname/
# lastname separately (Bedrock Agents caps functionSchema at 5 params).
OWNERS = {
    "9612f6c4-b7ff-4d82-b113-7b605e188ed9": {
        "firstname": "John",
        "lastname": "Doe",
    }
}

REQUIRED = ["ownerId", "date", "departureAirport", "arrivalAirport", "passengers"]


def lambda_handler(event, context):
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    missing = [f for f in REQUIRED if f not in params]
    if missing:
        body = json.dumps({"error": f"Missing required fields: {', '.join(missing)}"})
    else:
        owner_id = params["ownerId"]
        owner = OWNERS.get(owner_id, {"firstname": "Unknown", "lastname": "Owner"})

        passengers_raw = params.get("passengers", "[]")
        try:
            passengers = json.loads(passengers_raw) if isinstance(passengers_raw, str) else passengers_raw
        except (json.JSONDecodeError, TypeError):
            passengers = []

        confirmation = {
            "confirmationId": f"PVT-{uuid.uuid4().hex[:8].upper()}",
            "ownerId": owner_id,
            "primaryPassenger": f"{owner['firstname']} {owner['lastname']}",
            "date": params["date"],
            "departure": params["departureAirport"],
            "arrival": params["arrivalAirport"],
            "passengers": passengers,
            "totalPassengers": len(passengers) + 1,
            "status": "CONFIRMED",
            "bookedAt": datetime.utcnow().isoformat() + "Z",
        }
        body = json.dumps(confirmation)

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "function": event.get("function", ""),
            "functionResponse": {"responseBody": {"TEXT": {"body": body}}},
        },
    }
