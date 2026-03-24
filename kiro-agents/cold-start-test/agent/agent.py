import time
import os
import asyncio
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import httpx

app = BedrockAgentCoreApp()

MCP_SERVER_ARN = os.environ.get("MCP_SERVER_ARN", "")
REGION = os.environ.get("AWS_REGION", "us-west-2")


class SigV4Auth_HTTPX(httpx.Auth):
    """SigV4 authentication for HTTPX requests."""
    
    def __init__(self, credentials, service, region):
        self.credentials = credentials
        self.service = service
        self.region = region
    
    def auth_flow(self, request):
        # Create AWSRequest for signing
        body = request.content.decode() if request.content else ""
        aws_request = AWSRequest(method=request.method, url=str(request.url), data=body)
        aws_request.headers['Host'] = request.url.host
        
        # Sign the request
        signer = SigV4Auth(self.credentials, self.service, self.region)
        signer.add_auth(aws_request)
        
        # Update HTTPX request with signed headers
        for name, value in aws_request.headers.items():
            request.headers[name] = value
        
        yield request


def get_mcp_url(arn: str, region: str) -> str:
    """Build MCP server URL from ARN."""
    encoded_arn = arn.replace(':', '%3A').replace('/', '%2F')
    return f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"


@app.entrypoint
def invoke(payload, context):
    request_start = time.time()
    app.logger.info(f"Request received at {request_start}")
    
    prompt = payload.get("prompt", "test")
    
    async def call_mcp():
        mcp_start = time.time()
        
        # Get credentials and build URL
        session = boto3.Session()
        credentials = session.get_credentials()
        mcp_url = get_mcp_url(MCP_SERVER_ARN, REGION)
        
        app.logger.info(f"Connecting to MCP server: {mcp_url}")
        
        # Create SigV4 auth
        auth = SigV4Auth_HTTPX(credentials, 'bedrock-agentcore', REGION)
        
        async with streamablehttp_client(url=mcp_url, auth=auth) as (read, write, _):
            connect_time = time.time() - mcp_start
            app.logger.info(f"Connected in {connect_time:.3f}s")
            
            async with ClientSession(read, write) as session:
                await session.initialize()
                init_time = time.time() - mcp_start
                app.logger.info(f"Session initialized in {init_time:.3f}s")
                
                tools = await session.list_tools()
                tools_time = time.time() - mcp_start
                app.logger.info(f"Tools loaded in {tools_time:.3f}s - Found {len(tools.tools)} tools")
                
                # Call get_time tool
                result = await session.call_tool("get_time", {})
                call_time = time.time() - mcp_start
                tool_result = result.content[0].text if result.content else "No result"
                
                return {
                    "tool_result": tool_result,
                    "tools_found": len(tools.tools),
                    "connect_ms": round(connect_time * 1000),
                    "init_ms": round(init_time * 1000),
                    "tools_load_ms": round(tools_time * 1000),
                    "tool_call_ms": round(call_time * 1000)
                }
    
    try:
        mcp_result = asyncio.run(call_mcp())
        total_time = time.time() - request_start
        
        return {
            "prompt": prompt,
            "mcp_server_arn": MCP_SERVER_ARN,
            "mcp_result": mcp_result,
            "total_request_ms": round(total_time * 1000)
        }
    except Exception as e:
        app.logger.error(f"Error: {e}")
        import traceback
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "mcp_server_arn": MCP_SERVER_ARN,
            "total_ms": round((time.time() - request_start) * 1000)
        }

if __name__ == "__main__":
    app.run()
