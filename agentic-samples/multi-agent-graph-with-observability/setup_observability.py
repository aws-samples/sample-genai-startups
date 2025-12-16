#!/usr/bin/env python3
"""
Setup script for AgentCore Observability
Creates necessary CloudWatch resources and verifies configuration
"""

import json
import sys

import boto3
from botocore.exceptions import ClientError


def create_log_group(logs_client, log_group_name):
    """Create CloudWatch log group if it doesn't exist"""
    try:
        logs_client.create_log_group(logGroupName=log_group_name)
        print(f"Created log group: {log_group_name}")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceAlreadyExistsException":
            print(f"Log group already exists: {log_group_name}")
            return True
        print(f"ERROR: Error creating log group: {e}")
        return False


def create_log_stream(logs_client, log_group_name, log_stream_name):
    """Create CloudWatch log stream if it doesn't exist"""
    try:
        logs_client.create_log_stream(logGroupName=log_group_name, logStreamName=log_stream_name)
        print(f"Created log stream: {log_stream_name}")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceAlreadyExistsException":
            print(f"Log stream already exists: {log_stream_name}")
            return True
        print(f"ERROR: Error creating log stream: {e}")
        return False


def check_transaction_search(xray_client):
    """Check if Transaction Search is enabled"""
    try:
        response = xray_client.get_trace_segment_destination()
        destination = response.get("Destination")
        if destination == "CloudWatchLogs":
            print("Transaction Search is enabled (destination: CloudWatchLogs)")
            return True
        print(
            f"WARNING: Transaction Search destination is: {destination} (expected: CloudWatchLogs)"
        )
        return False
    except ClientError as e:
        print(f"ERROR: Error checking Transaction Search: {e}")
        return False


def enable_transaction_search(xray_client, logs_client, account_id, region):
    """Enable Transaction Search by creating policy and updating destination"""
    print("Enabling Transaction Search...")

    # Create resource policy
    policy_name = "InsuranceClaimsObservability"
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "TransactionSearchXRayAccess",
                "Effect": "Allow",
                "Principal": {"Service": "xray.amazonaws.com"},
                "Action": "logs:PutLogEvents",
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:aws/spans:*",
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/application-signals/data:*",
                ],
                "Condition": {
                    "ArnLike": {"aws:SourceArn": f"arn:aws:xray:{region}:{account_id}:*"},
                    "StringEquals": {"aws:SourceAccount": account_id},
                },
            }
        ],
    }

    try:
        logs_client.put_resource_policy(
            policyName=policy_name, policyDocument=json.dumps(policy_document)
        )
        print(f"Created resource policy: {policy_name}")
    except ClientError as e:
        print(f"WARNING: Error creating resource policy: {e}")

    # Update trace segment destination
    try:
        xray_client.update_trace_segment_destination(Destination="CloudWatchLogs")
        print("Updated trace segment destination to CloudWatchLogs")
    except ClientError as e:
        print(f"ERROR: Error updating trace destination: {e}")
        return False

    # Optional: Set sampling percentage to 1% (free tier)
    try:
        xray_client.update_indexing_rule(
            Name="Default", Rule={"Probabilistic": {"DesiredSamplingPercentage": 1}}
        )
        print("Set sampling percentage to 1% (free tier)")
    except ClientError as e:
        print(f"WARNING: Could not set sampling percentage: {e}")

    return True


def main():
    """Main setup function"""
    print("Setting up AgentCore Observability for claims-a Claims Assistant")

    # Initialize AWS clients
    try:
        session = boto3.Session()
        logs_client = session.client("logs")
        xray_client = session.client("xray")
        sts_client = session.client("sts")

        # Get account info
        identity = sts_client.get_caller_identity()
        account_id = identity["Account"]
        region = session.region_name

        print(f"AWS Account: {account_id}")
        print(f"Region: {region}")

    except Exception as e:
        print(f"ERROR: Error initializing AWS clients: {e}")
        print("ERROR: Please ensure AWS credentials are configured:")
        print("ERROR:   aws configure")
        sys.exit(1)

    # Configuration
    log_group_name = "/aws/claims-assistant"
    log_stream_name = "agent-traces"

    # Step 1: Create CloudWatch resources
    print("Step 1: Creating CloudWatch resources...")
    if not create_log_group(logs_client, log_group_name):
        sys.exit(1)

    if not create_log_stream(logs_client, log_group_name, log_stream_name):
        sys.exit(1)

    # Step 2: Check Transaction Search
    print("Step 2: Checking Transaction Search status...")
    if not check_transaction_search(xray_client):
        print("WARNING: Transaction Search is not enabled.")
        response = input("Would you like to enable it now? (y/n): ")
        if response.lower() == "y":
            if enable_transaction_search(xray_client, logs_client, account_id, region):
                print("Transaction Search enabled! Wait 10 minutes for spans to become available.")
            else:
                print("ERROR: Failed to enable Transaction Search.")
                print("ERROR: Please enable it manually via the CloudWatch console.") 
        else:
            print("You can enable Transaction Search later via:")
            print("  - CloudWatch Console (recommended)")
            print("  - AWS CLI")
    else:
        print("Transaction Search is already enabled")

    print("" + "=" * 60)
    print("Setup complete!")
    print("" + "=" * 60)
    print("Next steps:")
    print("1. Load observability configuration:")
    print("   source observability_config.sh")
    print("2. Run your application with instrumentation:")
    print("   uv run opentelemetry-instrument python sample-usage/car_claim.py")
    print("3. View traces in CloudWatch:")
    print(
        f"   https://console.aws.amazon.com/cloudwatch/home?region={region}#gen-ai-observability/"
    )


if __name__ == "__main__":
    main()
