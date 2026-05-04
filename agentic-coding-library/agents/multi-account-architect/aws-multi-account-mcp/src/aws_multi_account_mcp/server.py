from mcp.server.fastmcp import FastMCP
from . import tools

mcp = FastMCP("AWS Multi-Account MCP")

mcp.tool()(tools.audit_workloads)
mcp.tool()(tools.check_dependencies)
mcp.tool()(tools.get_migration_state)
mcp.tool()(tools.update_migration_state)
mcp.tool()(tools.write_migration_report)

def main():
    mcp.run(transport="stdio")
