#!/usr/bin/env python3
"""
Test script to verify AgentCore Gateway connection and OAuth authentication
"""
import requests
import json
import sys
import boto3
import re
import glob
from urllib.parse import urlparse

def test_retail_tools(access_token, gateway_url):
    """Test specific retail tools to list orders and other data"""
    
    print("\n🛍️ Testing retail tools...")
    
    # First, let's get the exact tool names
    print("   Getting available tools...")
    mcp_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list"
    }
    
    try:
        response = requests.post(
            gateway_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json=mcp_request,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if 'result' in data:
            tools = data['result'].get('tools', [])
            print(f"   Available tools:")
            for tool in tools:
                print(f"     - {tool.get('name', 'unnamed')}")
            
            # Look for listOrders tool specifically
            orders_tool = None
            for tool in tools:
                tool_name = tool.get('name', '')
                if 'listOrders' in tool_name:
                    orders_tool = tool_name
                    break
            
            if orders_tool:
                print(f"\n   Testing orders tool: {orders_tool}")
                mcp_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": orders_tool,
                        "arguments": {}
                    }
                }
            else:
                print(f"\n   No orders tool found, testing first available tool")
                orders_tool = tools[0].get('name', '')
                mcp_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": orders_tool,
                        "arguments": {}
                    }
                }
        else:
            print(f"   Could not get tools list: {data}")
            return None
            
    except Exception as e:
        print(f"   Error getting tools: {e}")
        return None
    
    # Test the orders/first tool
    
    try:
        response = requests.post(
            gateway_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json=mcp_request,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if 'result' in data:
            orders_result = data['result']
            if 'content' in orders_result:
                orders_content = orders_result['content']
                if isinstance(orders_content, list) and len(orders_content) > 0:
                    content_text = orders_content[0].get('text', '')
                    if 'Failed to fetch outbound api key' in content_text:
                        print(f"❌ Orders call failed with permission error:")
                        print(f"   Full error: {content_text}")
                        
                        # Check if there's debug info
                        if '_meta' in orders_result and 'debug' in orders_result['_meta']:
                            debug_text = orders_result['_meta']['debug'].get('text', '')
                            print(f"   Debug info: {debug_text}")
                        
                        return None
                    else:
                        print(f"✅ Orders retrieved successfully!")
                        print(f"   Response: {content_text[:200]}...")
                        return content_text
                else:
                    print(f"✅ Orders call successful but no data: {orders_result}")
            else:
                print(f"✅ Orders call successful: {orders_result}")
        else:
            print(f"❌ Orders call failed: {data}")
            
    except Exception as e:
        print(f"❌ Orders call failed: {e}")
    
    # Test 2: Check health (find the actual tool name)
    print("   Testing checkHealth...")
    health_tool_name = next((t['name'] for t in tools if 'checkHealth' in t['name']), None)
    if not health_tool_name:
        print("   ⚠️  checkHealth tool not found, skipping...")
    else:
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": health_tool_name,
                "arguments": {}
            }
        }
        
        try:
            response = requests.post(
                gateway_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=mcp_request,
            timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if 'result' in data:
                health_result = data['result']
                print(f"✅ Health check successful: {health_result}")
            else:
                print(f"❌ Health check failed: {data}")
                
        except Exception as e:
            print(f"❌ Health check failed: {e}")
    
    # Test 3: Get inventory (find the actual tool name)
    print("   Testing getInventory...")
    inventory_tool_name = next((t['name'] for t in tools if 'getInventory' in t['name'] or 'Inventory' in t['name']), None)
    if not inventory_tool_name:
        print("   ⚠️  getInventory tool not found, skipping...")
    else:
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": inventory_tool_name,
                "arguments": {}
            }
        }
        
        try:
            response = requests.post(
                gateway_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=mcp_request,
            timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if 'result' in data:
                inventory_result = data['result']
                if 'content' in inventory_result:
                    inventory_content = inventory_result['content']
                    if isinstance(inventory_content, list) and len(inventory_content) > 0:
                        content_text = inventory_content[0].get('text', '')
                        print(f"✅ Inventory retrieved successfully!")
                        print(f"   Response: {content_text[:200]}...")
                    else:
                    print(f"✅ Inventory call successful but no data: {inventory_result}")
            else:
                print(f"✅ Inventory call successful: {inventory_result}")
        else:
            print(f"❌ Inventory call failed: {data}")
            
    except Exception as e:
        print(f"❌ Inventory call failed: {e}")
    
    return None

def test_gateway_oauth(client_id, client_secret, token_endpoint, scope, gateway_url):
    """Test OAuth token retrieval and gateway connection"""
    
    print("🔐 Testing OAuth token retrieval...")
    
    # Step 1: Get OAuth token
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': scope
    }
    
    try:
        print(f"   Making request to: {token_endpoint}")
        print(f"   Client ID: {client_id}")
        print(f"   Scope: {scope}")
        
        token_response = requests.post(
            token_endpoint,
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
        
        if token_response.status_code != 200:
            print(f"   Response status: {token_response.status_code}")
            print(f"   Response body: {token_response.text}")
        
        token_response.raise_for_status()
        token_info = token_response.json()
        access_token = token_info['access_token']
        print(f"✅ OAuth token retrieved successfully")
        print(f"   Token expires in: {token_info.get('expires_in', 'unknown')} seconds")
        
    except Exception as e:
        print(f"❌ OAuth token retrieval failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response body: {e.response.text}")
        return False
    
    # Step 2: Test MCP connection
    print(f"\n🔗 Testing MCP connection to: {gateway_url}")
    
    mcp_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list"
    }
    
    try:
        mcp_response = requests.post(
            gateway_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json=mcp_request,
            timeout=30
        )
        mcp_response.raise_for_status()
        mcp_data = mcp_response.json()
        
        if 'result' in mcp_data:
            tools = mcp_data['result'].get('tools', [])
            print(f"✅ MCP connection successful!")
            print(f"   Found {len(tools)} tools:")
            for tool in tools[:5]:  # Show first 5 tools
                print(f"   - {tool.get('name', 'unnamed')}: {tool.get('description', 'no description')}")
            if len(tools) > 5:
                print(f"   ... and {len(tools) - 5} more tools")
            
            # Test retail tools
            test_retail_tools(access_token, gateway_url)
            
            return True
        else:
            print(f"❌ MCP connection failed: {mcp_data}")
            return False
            
    except Exception as e:
        print(f"❌ MCP connection failed: {e}")
        return False

def get_retail_cognito_info():
    """Get the retail demo Cognito configuration by auto-discovery"""
    
    print("🔍 Auto-discovering Cognito configuration from AWS...")
    
    try:
        import re
        domain_match = re.search(r'retail-demo-final-working-domain-([a-z0-9]+)', token_endpoint)
        if domain_match:
            domain_suffix = domain_match.group(1)
            print(f"   Found domain suffix: {domain_suffix}")
        
        # We'll need to discover the actual client ID
        region = "us-east-1"  # From the token endpoint
        cognito_client = boto3.client('cognito-idp', region_name=region)
        
        # List user pools to find the retail demo one
        paginator = cognito_client.get_paginator('list_user_pools')
        user_pools = []
        
        for page in paginator.paginate(MaxResults=60):
            user_pools.extend(page['UserPools'])
        
        # Look for retail-related user pool
        retail_pool = None
        for pool in user_pools:
            pool_name = pool['Name'].lower()
            if 'retail' in pool_name or 'demo' in pool_name:
                retail_pool = pool
                print(f"   Found retail user pool: {pool['Name']}")
                break
        
        if not retail_pool:
            print("❌ Could not find retail demo user pool")
            return None
        
        user_pool_id = retail_pool['Id']
        
        # Get user pool clients
        clients_response = cognito_client.list_user_pool_clients(
            UserPoolId=user_pool_id,
            MaxResults=60
        )
        
        if not clients_response['UserPoolClients']:
            print("❌ No clients found in user pool")
            return None
        
        # The client ID is actually the first part of the provided string before the token endpoint
        # Let's extract it properly from the original string
        # The format appears to be: client_id + client_secret + token_endpoint
        
        # Try to find the actual client ID by looking at the clients
        actual_client_id = None
        for client in clients_response['UserPoolClients']:
            client_id_from_aws = client['ClientId']
            # Check if this client ID appears at the start of our provided string
            if provided_info.startswith(client_id_from_aws):
                actual_client_id = client_id_from_aws
                # Recalculate the client secret by removing the client ID from the start
                remaining = provided_info[len(client_id_from_aws):]
                if "https://" in remaining:
                    client_secret = remaining.split("https://")[0]
                print(f"   Found matching client ID: {actual_client_id}")
                print(f"   Recalculated client secret: {client_secret[:20]}...")
                break
        
        if not actual_client_id:
            # Fallback to the discovered client ID
            actual_client_id = clients_response['UserPoolClients'][0]['ClientId']
            print(f"   Using discovered client ID: {actual_client_id}")
        
        print(f"   Token endpoint: {token_endpoint}")
        
        # Try to get the actual scopes from the client configuration
        try:
            client_details = cognito_client.describe_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=actual_client_id
            )
            
            client_config = client_details['UserPoolClient']
            allowed_scopes = client_config.get('AllowedOAuthScopes', [])
            
            if allowed_scopes:
                print(f"   Available scopes: {allowed_scopes}")
                # Use the first available scope, or look for a gateway-related one
                if 'https://agentcore.amazonaws.com/gateway' in allowed_scopes:
                    scope = 'https://agentcore.amazonaws.com/gateway'
                elif any('gateway' in s.lower() for s in allowed_scopes):
                    scope = next(s for s in allowed_scopes if 'gateway' in s.lower())
                else:
                    scope = allowed_scopes[0]
                print(f"   Using scope: {scope}")
            else:
                # Try common scopes
                scope = "openid"
                print(f"   No scopes configured, trying: {scope}")
                
        except Exception as e:
            print(f"   Could not get client scopes: {e}")
            scope = "openid"
        
        return {
            'client_id': actual_client_id,
            'client_secret': client_secret,
            'token_endpoint': token_endpoint,
            'scope': scope,
            'user_pool_id': user_pool_id,
            'region': region
        }
        
    except Exception as e:
        print(f"❌ Error getting retail Cognito info: {e}")
        print("   Falling back to manual configuration...")
        
        # Fallback - use what we can parse
        return {
            'client_id': None,  # Will need to be provided manually
            'client_secret': client_secret,
            'token_endpoint': token_endpoint,
            'scope': "https://agentcore.amazonaws.com/gateway",
            'user_pool_id': None,
            'region': "us-east-1"
        }

def main():
    print("AgentCore Gateway Connection Test")
    print("=" * 40)
    
    # Check if gateway URL provided as argument
    if len(sys.argv) > 1:
        gateway_url = sys.argv[1]
    else:
        # Try to read from config file
        import glob
        config_files = glob.glob("agentcore-integration/retail_gateway_config_boto3_*.json")
        if config_files:
            print(f"📄 Found config file: {config_files[0]}")
            try:
                with open(config_files[0], 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    gateway_url = config.get('gateway_url')
                    print(f"✅ Loaded gateway URL from config file")
            except Exception as e:
                print(f"❌ Error reading config file: {e}")
                gateway_url = None
        else:
            gateway_url = None
        
        if not gateway_url:
            print("\n❌ No gateway URL found!")
            print("\nUsage:")
            print("  python test_gateway_connection.py <gateway_url>")
            print("\nOr place a retail_gateway_config_boto3_*.json file in agentcore-integration/")
            print("\nExample:")
            print("  python test_gateway_connection.py https://your-gateway-id.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp")
            sys.exit(1)
    
    print(f"Gateway URL: {gateway_url}")
    
    # Get retail demo Cognito configuration
    cognito_info = get_retail_cognito_info()
    
    if not cognito_info:
        print("\n❌ Could not automatically discover Cognito configuration")
        print("Please provide credentials manually:")
        
        client_id = input("Client ID: ").strip()
        client_secret = input("Client Secret: ").strip()
        token_endpoint = input("Token Endpoint: ").strip()
        scope = input("Scope: ").strip()
        
        if not all([client_id, client_secret, token_endpoint, scope]):
            print("❌ All credentials are required!")
            sys.exit(1)
    else:
        print(f"\n✅ Discovered Cognito configuration:")
        print(f"   Client ID: {cognito_info['client_id']}")
        print(f"   Token Endpoint: {cognito_info['token_endpoint']}")
        print(f"   Scope: {cognito_info['scope']}")
        
        client_id = cognito_info['client_id']
        client_secret = cognito_info['client_secret']
        token_endpoint = cognito_info['token_endpoint']
        scope = cognito_info['scope']
        
        if not client_secret:
            print("❌ Client secret is required but not available")
            sys.exit(1)
        
        if not client_id:
            print("❌ Could not determine client ID automatically")
            client_id = input("Please enter the client ID: ").strip()
            if not client_id:
                sys.exit(1)
    
    # Test the connection
    success = test_gateway_oauth(client_id, client_secret, token_endpoint, scope, gateway_url)
    
    if success:
        print("\n🎉 Gateway is working correctly!")
        print("\nConfiguration for QuickSuite:")
        print(f"   Client ID: {client_id}")
        print(f"   Client Secret: {client_secret}")
        print(f"   Token Endpoint: {token_endpoint}")
        print(f"   Scope: {scope}")
        print(f"   MCP Endpoint: {gateway_url}")
    else:
        print("\n❌ Gateway connection failed. Please check the configuration.")

if __name__ == "__main__":
    main()