import json
import os
import unittest

from mcp_helpers import MCPConfigurationError, locate_config


class MCPConfigurationSecurityTests(unittest.TestCase):
    def setUp(self):
        self.previous_registry = os.environ.get("MCP_SERVERS_JSON")
        os.environ["MCP_SERVERS_JSON"] = json.dumps(
            {
                "safe-server": {
                    "command": "/opt/mcp/safe-server",
                    "args": ["--stdio"],
                    "env": {"SAFE_MODE": "1"},
                }
            }
        )

    def tearDown(self):
        if self.previous_registry is None:
            os.environ.pop("MCP_SERVERS_JSON", None)
        else:
            os.environ["MCP_SERVERS_JSON"] = self.previous_registry

    def test_request_cannot_supply_process_parameters(self):
        with self.assertRaises(MCPConfigurationError):
            locate_config(
                {
                    "server": "safe-server",
                    "command": "/bin/sh",
                    "args": ["-c", "id"],
                    "env": {},
                }
            )

    def test_registry_supplies_process_parameters(self):
        self.assertEqual(
            locate_config({"server": "safe-server", "disabled_tools": ["one"]}),
            (
                "/opt/mcp/safe-server",
                ["--stdio"],
                {"SAFE_MODE": "1"},
                ["one"],
            ),
        )

    def test_unknown_server_is_rejected(self):
        with self.assertRaises(MCPConfigurationError):
            locate_config({"server": "not-configured"})


if __name__ == "__main__":
    unittest.main()
