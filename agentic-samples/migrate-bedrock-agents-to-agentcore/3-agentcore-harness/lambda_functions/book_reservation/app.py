import uuid
from datetime import datetime


def lambda_handler(event, context):
    required = ["ownerId", "firstname", "lastname", "date",
                "departureAirport", "arrivalAirport"]
    missing = [f for f in required if f not in event]
    if missing:
        return {"error": f"Missing required fields: {', '.join(missing)}"}

    return {
        "confirmationId": f"PVT-{uuid.uuid4().hex[:8].upper()}",
        "ownerId": event["ownerId"],
        "primaryPassenger": f"{event['firstname']} {event['lastname']}",
        "date": event["date"],
        "departure": event["departureAirport"],
        "arrival": event["arrivalAirport"],
        "passengers": event.get("passengers", []),
        "totalPassengers": len(event.get("passengers", [])) + 1,
        "status": "CONFIRMED",
        "bookedAt": datetime.utcnow().isoformat() + "Z",
    }
