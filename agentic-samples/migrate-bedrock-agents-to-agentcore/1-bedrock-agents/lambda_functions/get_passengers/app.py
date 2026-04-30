import json


PASSENGERS = {
    "9612f6c4-b7ff-4d82-b113-7b605e188ed9": [
        {"firstname": "Jill", "lastname": "Doe", "homeAirport": "KJFK",
         "ownerRelationship": "Wife", "age": 39},
        {"firstname": "Jane", "lastname": "Doe", "homeAirport": "KJFK",
         "ownerRelationship": "Daughter", "age": 20},
        {"firstname": "Jenny", "lastname": "Doe", "homeAirport": "KJFK",
         "ownerRelationship": "Daughter", "age": 24},
    ]
}


def lambda_handler(event, context):
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}
    owner_id = params.get("ownerId")

    if owner_id and owner_id in PASSENGERS:
        body = json.dumps({"ownerId": owner_id, "passengers": PASSENGERS[owner_id]})
    else:
        body = json.dumps({"error": f"No passengers found for owner '{owner_id}'."})

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "function": event.get("function", ""),
            "functionResponse": {"responseBody": {"TEXT": {"body": body}}},
        },
    }
