"""Delete the Lambda tool backends and their execution role.

Run after `agentcore` has torn down the Harness and Gateway — this script
only cleans up the Lambda resources this repo created directly.
"""
import boto3

from _state import (
    LAMBDA_FUNCTION_PREFIX,
    LAMBDA_ROLE_NAME,
    REGION,
    STATE_PATH,
    TOOLS,
    load_state,
)


def main():
    state = load_state()

    lam = boto3.client("lambda", region_name=REGION)
    for tool in TOOLS:
        name = f"{LAMBDA_FUNCTION_PREFIX}-{tool}"
        try:
            lam.delete_function(FunctionName=name)
            print(f"Deleted {name}")
        except lam.exceptions.ResourceNotFoundException:
            pass

    iam = boto3.client("iam")
    try:
        for p in iam.list_attached_role_policies(RoleName=LAMBDA_ROLE_NAME)["AttachedPolicies"]:
            iam.detach_role_policy(RoleName=LAMBDA_ROLE_NAME, PolicyArn=p["PolicyArn"])
        iam.delete_role(RoleName=LAMBDA_ROLE_NAME)
        print(f"Deleted role: {LAMBDA_ROLE_NAME}")
    except iam.exceptions.NoSuchEntityException:
        pass

    if STATE_PATH.exists():
        STATE_PATH.unlink()
        print(f"Removed {STATE_PATH.name}")


if __name__ == "__main__":
    main()
