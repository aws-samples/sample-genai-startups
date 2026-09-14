import json


OWNERS = {
    "9612f6c4-b7ff-4d82-b113-7b605e188ed9": {
        "id": "9612f6c4-b7ff-4d82-b113-7b605e188ed9",
        "firstname": "John",
        "lastname": "Doe",
        "homeAirport": "KJFK",
    }
}


def lambda_handler(event, context):
    # functionSchema event shape:
    #   parameters: [{"name": "ownerId", "type": "string", "value": "..."}]
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}
    owner_id = params.get("ownerId")

    if owner_id and owner_id in OWNERS:
        body = json.dumps(OWNERS[owner_id])
    else:
        body = json.dumps({"error": f"Owner '{owner_id}' not found."})

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "function": event.get("function", ""),
            "functionResponse": {"responseBody": {"TEXT": {"body": body}}},
        },
    }
