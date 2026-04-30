#!/usr/bin/env python3
"""
Generate the updated OpenAPI specification with PUT and DELETE operations
"""

import json
import sys
sys.path.append('.')

from deploy_retail_gateway_boto3 import RetailGatewayDeployerBoto3

# Create deployer instance
deployer = RetailGatewayDeployerBoto3()

# Generate OpenAPI spec
openapi_spec = deployer.generate_openapi_spec("https://api.yourcompany.com")

# Save to file
with open('agentcore-integration/openapi-spec.json', 'w', encoding='utf-8') as f:
    json.dump(openapi_spec, f, indent=2)

print("✅ OpenAPI specification generated and saved to openapi-spec.json")
print(f"   Total endpoints: {len(openapi_spec['paths'])}")
print(f"   Total operations: {sum(len(methods) for methods in openapi_spec['paths'].values())}")
