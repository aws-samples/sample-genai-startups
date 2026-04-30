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
    # AgentCore Gateway invokes this Lambda with the MCP tool arguments
    # surfaced directly on the event payload.
    owner_id = event.get("owner_id") or event.get("ownerId")

    if owner_id and owner_id in OWNERS:
        return OWNERS[owner_id]
    return {"error": f"Owner '{owner_id}' not found."}
