"""MCP server for Bedrock model operations."""
from mcp.server.fastmcp import FastMCP

from . import models

mcp = FastMCP("Bedrock Model MCP")

mcp.tool()(models.get_model_providers)
mcp.tool()(models.search_models)
mcp.tool()(models.list_inference_profiles)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
