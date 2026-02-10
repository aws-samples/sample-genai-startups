#!/usr/bin/env python3
"""
Script to update the Gateway Service Role policy with the correct resource
"""
import boto3
import json
import sys
import os

def update_gateway_policy(role_name=None, gateway_id=None):
    """Update the existing policy with the correct resource"""
    
    # Get AWS account ID and region dynamically
    sts = boto3.client('sts')
    account_id = sts.get_caller_identity()['Account']
    region = os.environ.get('AWS_REGION', boto3.session.Session().region_name or 'us-east-1')
    
    # If role_name not provided, try to find it
    if not role_name:
        print("🔍 Searching for AgentCore Gateway service role...")
        iam = boto3.client('iam')
        try:
            roles = iam.list_roles()
            for role in roles['Roles']:
                if 'AmazonBedrockAgentCoreGatewayServiceRole' in role['RoleName']:
                    role_name = role['RoleName']
                    print(f"✅ Found role: {role_name}")
                    break
        except Exception as e:
            print(f"❌ Error finding role: {e}")
            print("Please provide role name as argument: python update_gateway_policy.py <role_name> [gateway_id]")
            sys.exit(1)
    
    if not role_name:
        print("❌ No AgentCore Gateway service role found")
        print("Usage: python update_gateway_policy.py <role_name> [gateway_id]")
        sys.exit(1)
    
    policy_name = "WorkloadIdentityTokenAccess"
    
    # Both resources based on the error message
    workload_identity_directory = f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default"
    
    # If gateway_id provided, use it; otherwise use wildcard
    if gateway_id:
        specific_workload_resource = f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/{gateway_id}"
    else:
        specific_workload_resource = f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/*"
    
    print("🔄 Updating Gateway Service Role Policy...")
    print(f"Account ID: {account_id}")
    print(f"Region: {region}")
    print(f"Role: {role_name}")
    print(f"Policy: {policy_name}")
    print("-" * 60)
    
    iam = boto3.client('iam')
    
    # API key resources - use wildcards for flexibility
    api_key_resource = f"arn:aws:bedrock-agentcore:{region}:{account_id}:token-vault/default/apikeycredentialprovider/*"
    token_vault_resource = f"arn:aws:bedrock-agentcore:{region}:{account_id}:token-vault/default"
    
    # Create the updated policy document with all required permissions
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "bedrock-agentcore:GetWorkloadAccessToken",
                "Resource": [
                    workload_identity_directory,
                    specific_workload_resource
                ]
            },
            {
                "Effect": "Allow",
                "Action": "bedrock-agentcore:GetResourceApiKey",
                "Resource": [
                    api_key_resource,
                    token_vault_resource,  # Also needs GetResourceApiKey on token vault
                    workload_identity_directory,  # Also needs GetResourceApiKey on workload identity directory
                    specific_workload_resource  # Also needs GetResourceApiKey on workload identity
                ]
            },
            {
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": f"arn:aws:secretsmanager:{region}:{account_id}:secret:*"
            }
        ]
    }
    
    try:
        # Update the policy
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document)
        )
        
        print("✅ Policy updated successfully!")
        print("Updated policy content:")
        print(json.dumps(policy_document, indent=2))
        
        # Verify the update
        print("\n🔍 Verifying update...")
        policy_doc = iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)
        retrieved_policy = policy_doc['PolicyDocument']
        
        print("✅ Verification successful!")
        print("Current policy content:")
        print(json.dumps(retrieved_policy, indent=2))
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to update policy: {e}")
        return False

if __name__ == "__main__":
    # Parse command line arguments
    role_name = sys.argv[1] if len(sys.argv) > 1 else None
    gateway_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not role_name and len(sys.argv) == 1:
        print("Usage: python update_gateway_policy.py [role_name] [gateway_id]")
        print("\nIf no arguments provided, will auto-discover the role.")
        print("Gateway ID is optional - if not provided, will use wildcard for all gateways.")
        print("\nExamples:")
        print("  python update_gateway_policy.py")
        print("  python update_gateway_policy.py AmazonBedrockAgentCoreGatewayServiceRole-abc123")
        print("  python update_gateway_policy.py AmazonBedrockAgentCoreGatewayServiceRole-abc123 retail-demo-xyz789")
        print()
    
    success = update_gateway_policy(role_name, gateway_id)
    
    if success:
        print(f"\n🎉 Policy update complete!")
        print(f"The gateway should now have access to:")
        print(f"  1. The workload identity directory")
        print(f"  2. All workload identities (or specific one if provided)")
        print(f"  3. API key credential providers")
        print(f"  4. Secrets Manager")
        print(f"\nTry testing the gateway again in a few minutes.")
    else:
        print(f"\n❌ Policy update failed!")