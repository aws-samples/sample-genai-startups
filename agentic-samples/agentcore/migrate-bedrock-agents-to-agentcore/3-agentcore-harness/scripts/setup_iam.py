"""Create the Lambda execution role.

The Gateway execution role and Harness execution role are created by the
AgentCore CLI during `agentcore deploy` via the CDK stack — only the
Lambda role is owned by this script.
"""
import json
import time

import boto3

from _state import LAMBDA_ROLE_NAME, load_state, save_state


TRUST_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }],
})

LAMBDA_MANAGED_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"


def ensure_lambda_role() -> str:
    iam = boto3.client("iam")
    try:
        role = iam.get_role(RoleName=LAMBDA_ROLE_NAME)["Role"]
        print(f"  using existing role: {role['Arn']}")
        return role["Arn"]
    except iam.exceptions.NoSuchEntityException:
        pass

    role = iam.create_role(
        RoleName=LAMBDA_ROLE_NAME,
        AssumeRolePolicyDocument=TRUST_POLICY,
        Description="Basic execution role for private-aviation Lambda tools",
    )
    iam.attach_role_policy(RoleName=LAMBDA_ROLE_NAME, PolicyArn=LAMBDA_MANAGED_POLICY)
    print("  created — waiting 10s for IAM propagation...")
    time.sleep(10)
    return role["Role"]["Arn"]


def main():
    print("Ensuring Lambda execution role...")
    state = load_state()
    state["lambda_role_arn"] = ensure_lambda_role()
    save_state(state)
    print("Done.")


if __name__ == "__main__":
    main()
