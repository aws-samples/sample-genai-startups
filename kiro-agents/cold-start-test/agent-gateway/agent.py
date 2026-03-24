import time
import os
import asyncio
import requests
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

app = BedrockAgentCoreApp()

GATEWAY_URL = os.environ.get("GATEWAY_URL", "")
COGNITO_TOKEN_URL = os.environ.get("COGNITO_TOKEN_URL", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
COGNITO_CLIENT_SECRET = os.environ.get("COGNITO_CLIENT_SECRET", "")
COGNITO_SCOPE = os.environ.get("COGNITO_SCOPE", "")


def get_cognito_token():
    response = requests.post(
        COGNITO_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": COGNITO_CLIENT_ID,
            "client_secret": COGNITO_CLIENT_SECRET,
            "scope": COGNITO_SCOPE
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    return response.json().get("access_token")


@app.entrypoint
def invoke(payload, context):
    request_start = time.time()
    prompt = payload.get("prompt", "test")
    
    async def call_mcp():
        mcp_start = time.time()
        
        token = get_cognito_token()
        token_time = time.time() - mcp_start
        
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            async with streamablehttp_client(url=GATEWAY_URL, headers=headers) as (read, write, _):
                connect_time = time.time() - mcp_start
                
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    init_time = time.time() - mcp_start
                    
                    tools = await session.list_tools()
                    tools_time = time.time() - mcp_start
                    tool_names = [t.name for t in tools.tools]
                    
                    # Try to call first available tool
                    tool_result = "skipped"
                    call_time = tools_time
                    if tool_names:
                        try:
                            result = await session.call_tool(tool_names[0], {"location": "Seattle"})
                            call_time = time.time() - mcp_start
                            tool_result = str(result.content[0].text)[:100] if result.content else "empty"
                        except Exception as e:
                            call_time = time.time() - mcp_start
                            tool_result = f"call_error: {e}"
                    
                    return {
                        "tool_result": tool_result,
                        "tools_found": tool_names,
                        "token_ms": round(token_time * 1000),
                        "connect_ms": round((connect_time - token_time) * 1000),
                        "init_ms": round((init_time - connect_time) * 1000),
                        "tools_load_ms": round((tools_time - init_time) * 1000),
                        "tool_call_ms": round((call_time - tools_time) * 1000),
                        "total_mcp_ms": round(call_time * 1000)
                    }
        except Exception as e:
            return {"error": str(e), "token_ms": round(token_time * 1000)}
    
    mcp_result = asyncio.run(call_mcp())
    total_time = time.time() - request_start
    
    return {
        "prompt": prompt,
        "mcp_result": mcp_result,
        "total_request_ms": round(total_time * 1000)
    }

if __name__ == "__main__":
    app.run()
