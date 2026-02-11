#!/usr/bin/env python3
"""
Test all retail tools to see which ones work
"""
import requests
import json
import sys
import boto3
import re
import glob
from urllib.parse import urlparse

def get_retail_cognito_info():
    """Get the retail demo Cognito configuration by auto-discovery"""
    
    print("🔍 Auto-discovering Cognito configuration from AWS...")
    
    try:
        region = "us-east-1"
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
        return None

def get_access_token(cognito_info):
    """Get OAuth access token"""
    
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': cognito_info['client_id'],
        'client_secret': cognito_info['client_secret'],
        'scope': cognito_info['scope']
    }
    
    try:
        token_response = requests.post(
            cognito_info['token_endpoint'],
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
        token_response.raise_for_status()
        token_info = token_response.json()
        return token_info['access_token']
        
    except Exception as e:
        print(f"❌ Failed to get access token: {e}")
        return None

def test_retail_tool(access_token, gateway_url, tool_name, arguments=None):
    """Test a specific retail tool"""
    
    if arguments is None:
        arguments = {}
    
    mcp_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
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
            result = data['result']
            if 'content' in result:
                content = result['content']
                if isinstance(content, list) and len(content) > 0:
                    content_text = content[0].get('text', '')
                    
                    # Check for various error conditions
                    if 'Failed to fetch outbound api key' in content_text:
                        return {"status": "permission_error", "error": content_text}
                    elif 'OpenAPIClientException' in content_text:
                        return {"status": "api_error", "error": content_text}
                    elif 'Error executing HTTP request' in content_text:
                        return {"status": "http_error", "error": content_text}
                    elif content_text.strip():
                        return {"status": "success", "data": content_text}
                    else:
                        return {"status": "empty_response", "data": ""}
                else:
                    return {"status": "success", "data": result}
            else:
                return {"status": "success", "data": result}
        else:
            return {"status": "error", "error": data}
            
    except Exception as e:
        return {"status": "exception", "error": str(e)}

def main():
    print("Retail Tools Comprehensive Test")
    print("=" * 50)
    
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
            print("  python test_all_retail_tools.py <gateway_url>")
            print("\nOr place a retail_gateway_config_boto3_*.json file in agentcore-integration/")
            print("\nExample:")
            print("  python test_all_retail_tools.py https://your-gateway-id.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp")
            sys.exit(1)
    
    # Get Cognito configuration
    cognito_info = get_retail_cognito_info()
    if not cognito_info:
        print("❌ Failed to get Cognito configuration")
        sys.exit(1)
    
    # Get access token
    print(f"\n🔐 Getting access token...")
    access_token = get_access_token(cognito_info)
    if not access_token:
        print("❌ Failed to get access token")
        sys.exit(1)
    
    print(f"✅ Access token obtained")
    
    # First, discover available tools from the gateway
    print(f"\n🔍 Discovering available tools from gateway...")
    try:
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }
        
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
        
        available_tools = []
        if 'result' in data and 'tools' in data['result']:
            for tool in data['result']['tools']:
                tool_name = tool.get('name', '')
                # Filter for retail API tools
                if 'checkHealth' in tool_name or 'list' in tool_name or 'get' in tool_name or \
                   'update' in tool_name or 'delete' in tool_name or 'create' in tool_name:
                    available_tools.append((tool_name, {}))
            
            print(f"✅ Found {len(available_tools)} retail tools")
        else:
            print("⚠️  Could not discover tools, using default list")
            # Fallback to generic tool names (without target prefix)
            available_tools = [
                ("checkHealth", {}),
            timeout=30
                ("listOrders", {}),
            timeout=30
                ("listCustomers", {}),
            timeout=30
                ("listProducts", {}),
            timeout=30
                ("listPurchases", {}),
            timeout=30
                ("getInventory", {}),
            timeout=30
                ("getSalesAnalytics", {}),
            timeout=30
                ("updateOrder", {}),
            timeout=30
                ("updateProduct", {}),
            timeout=30
                ("updateCustomer", {}),
            timeout=30
                ("deleteOrder", {}),
            timeout=30
                ("deleteProduct", {}),
            timeout=30
                ("deleteCustomer", {}),
            timeout=30
            ]
    except Exception as e:
        print(f"⚠️  Error discovering tools: {e}")
        print("Using default tool list...")
        available_tools = [
            ("checkHealth", {}),
            timeout=30
            ("listOrders", {}),
            timeout=30
            ("listCustomers", {}),
            timeout=30
            ("listProducts", {}),
            timeout=30
            ("listPurchases", {}),
            timeout=30
            ("getInventory", {}),
            timeout=30
            ("getSalesAnalytics", {}),
            timeout=30
            ("updateOrder", {}),
            timeout=30
            ("updateProduct", {}),
            timeout=30
            ("updateCustomer", {}),
            timeout=30
            ("deleteOrder", {}),
            timeout=30
            ("deleteProduct", {}),
            timeout=30
            ("deleteCustomer", {}),
            timeout=30
        ]
    
    retail_tools = available_tools
    ]
    
    print(f"\n🛍️ Testing {len(retail_tools)} retail tools (including new PUT/DELETE operations)...")
    print("-" * 50)
    
    results = {}
    
    for tool_name, arguments in retail_tools:
        print(f"\n🔧 Testing: {tool_name}")
        result = test_retail_tool(access_token, gateway_url, tool_name, arguments)
        results[tool_name] = result
        
        if result['status'] == 'success':
            print(f"   ✅ SUCCESS")
            data = result['data']
            if isinstance(data, str):
                print(f"   📄 Data: {data[:100]}{'...' if len(data) > 100 else ''}")
            else:
                print(f"   📄 Data: {str(data)[:100]}{'...' if len(str(data)) > 100 else ''}")
        elif result['status'] == 'permission_error':
            print(f"   🔒 PERMISSION ERROR")
            print(f"   📄 Error: {result['error'][:100]}...")
        elif result['status'] == 'api_error':
            print(f"   🌐 API ERROR")
            print(f"   📄 Error: {result['error'][:100]}...")
        elif result['status'] == 'http_error':
            print(f"   🔗 HTTP ERROR")
            print(f"   📄 Error: {result['error'][:100]}...")
        else:
            print(f"   ❌ ERROR ({result['status']})")
            print(f"   📄 Error: {result.get('error', 'Unknown error')[:100]}...")
    
    # Summary
    print(f"\n📊 SUMMARY")
    print("=" * 50)
    
    success_count = sum(1 for r in results.values() if r['status'] == 'success')
    total_count = len(results)
    
    print(f"✅ Successful tools: {success_count}/{total_count}")
    
    if success_count > 0:
        print(f"\n🎉 Working tools:")
        for tool_name, result in results.items():
            if result['status'] == 'success':
                print(f"   - {tool_name}")
    
    if success_count < total_count:
        print(f"\n❌ Failed tools:")
        for tool_name, result in results.items():
            if result['status'] != 'success':
                print(f"   - {tool_name}: {result['status']}")
    
    print(f"\n🔧 Configuration for QuickSuite:")
    print(f"   Client ID: {cognito_info['client_id']}")
    print(f"   Client Secret: {cognito_info['client_secret']}")
    print(f"   Token Endpoint: {cognito_info['token_endpoint']}")
    print(f"   Scope: {cognito_info['scope']}")
    print(f"   MCP Endpoint: {gateway_url}")

if __name__ == "__main__":
    main()