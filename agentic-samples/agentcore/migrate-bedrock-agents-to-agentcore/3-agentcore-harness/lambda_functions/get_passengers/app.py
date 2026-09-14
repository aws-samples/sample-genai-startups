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
    owner_id = event.get("owner_id") or event.get("ownerId")

    if owner_id and owner_id in PASSENGERS:
        return {"ownerId": owner_id, "passengers": PASSENGERS[owner_id]}
    return {"error": f"No passengers found for owner '{owner_id}'."}
