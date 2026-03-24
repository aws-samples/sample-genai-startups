import time
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(host="0.0.0.0", stateless_http=True)
START_TIME = time.time()

@mcp.tool()
def get_time() -> str:
    """Get current server time and uptime"""
    return f"Server uptime: {time.time() - START_TIME:.2f}s"

@mcp.tool()
def echo(message: str) -> str:
    """Echo a message back with timestamp"""
    return f"[{time.time():.3f}] {message}"

if __name__ == "__main__":
    print(f"MCP Server starting at {time.time()}")
    mcp.run(transport="streamable-http")
