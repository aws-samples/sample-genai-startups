import json
import os
import re
from typing import Any


class MCPConfigurationError(ValueError):
    """Raised when an MCP configuration is not safe to execute."""


def parse_config(config_str):
    """Parse tool configuration with recovery for malformed JSON."""
    if not config_str:
        return {}
    
    try:
        return json.loads(config_str)
    except Exception:
        return _recover_json(config_str)


def _load_server_registry():
    """Load the operator-owned MCP server registry."""
    raw_registry = os.environ.get("MCP_SERVERS_JSON", "{}")
    try:
        registry = json.loads(raw_registry)
    except json.JSONDecodeError as exc:
        raise MCPConfigurationError("MCP_SERVERS_JSON is not valid JSON") from exc

    if not isinstance(registry, dict):
        raise MCPConfigurationError("MCP_SERVERS_JSON must be a JSON object")
    return registry


def _validate_server_definition(server_id: str, definition: Any):
    if not isinstance(definition, dict):
        raise MCPConfigurationError(f"MCP server '{server_id}' has an invalid definition")

    command = definition.get("command")
    args = definition.get("args", [])
    env = definition.get("env", {})

    # Require a fixed executable path from the operator-owned registry. The
    # request is never allowed to select an executable, arguments, or env.
    if not isinstance(command, str) or not command.startswith("/"):
        raise MCPConfigurationError(
            f"MCP server '{server_id}' must define an absolute command path"
        )
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise MCPConfigurationError(f"MCP server '{server_id}' args must be a string list")
    if not isinstance(env, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in env.items()
    ):
        raise MCPConfigurationError(f"MCP server '{server_id}' env must be a string map")

    return command, args, env


def _find_server_reference(config_dict):
    if not isinstance(config_dict, dict):
        return None

    if "command" in config_dict or "args" in config_dict or "env" in config_dict:
        raise MCPConfigurationError(
            "MCP commands must be selected by server ID; command, args, and env "
            "cannot be supplied by the request"
        )

    if "server" in config_dict:
        server_id = config_dict["server"]
        if not isinstance(server_id, str) or not server_id:
            raise MCPConfigurationError("MCP server must be a non-empty server ID")
        return server_id, config_dict.get("disabled_tools", [])

    for value in config_dict.values():
        if isinstance(value, dict):
            result = _find_server_reference(value)
            if result:
                return result
    return None

def locate_config(config_dict):
    """Resolve an MCP server from the operator-owned registry.

    Stored/user-provided tool configuration may select only a server ID and
    disabled tool names. Process execution parameters come exclusively from
    MCP_SERVERS_JSON.
    """
    reference = _find_server_reference(config_dict)
    if not reference:
        raise MCPConfigurationError(
            "MCP configuration must contain a server ID from the server registry"
        )

    server_id, disabled_tools = reference
    if not isinstance(disabled_tools, list) or not all(
        isinstance(tool, str) for tool in disabled_tools
    ):
        raise MCPConfigurationError("disabled_tools must be a string list")

    registry = _load_server_registry()
    definition = registry.get(server_id)
    if definition is None:
        raise MCPConfigurationError(f"MCP server '{server_id}' is not configured")

    command, args, env = _validate_server_definition(server_id, definition)
    return command, args, env, disabled_tools

def _recover_json(malformed_json):
    """Attempt to recover a dictionary from malformed JSON."""
    if not malformed_json:
        return {}
        
    # Strategy 1: Fix common syntax errors
    fixed_json = malformed_json.strip()
    
    # Fix trailing commas in objects and arrays
    fixed_json = re.sub(r',\s*}', '}', fixed_json)
    fixed_json = re.sub(r',\s*]', ']', fixed_json)
    
    # Fix missing quotes around keys
    fixed_json = re.sub(r'(\{|\,)\s*([a-zA-Z0-9_]+)\s*:', r'\1"\2":', fixed_json)
    
    if not fixed_json.startswith('{') and not fixed_json.startswith("["): 
        fixed_json = '{' + fixed_json + '}'

    # Try to parse the fixed JSON
    try:
        return json.loads(fixed_json)
    except:
        pass
        
    # Strategy 2: Use regex to extract key-value pairs
    try:
        result = {}
        # Match "key": value patterns (string values)
        string_pattern = r'"([^"]+)"\s*:\s*"([^"]*)"'
        for match in re.finditer(string_pattern, malformed_json):
            key, value = match.groups()
            result[key] = value
            
        # Match "key": value patterns (numeric values)
        num_pattern = r'"([^"]+)"\s*:\s*(-?\d+(?:\.\d+)?)'
        for match in re.finditer(num_pattern, malformed_json):
            key, value = match.groups()
            try:
                # Convert to int or float as appropriate
                if '.' in value:
                    result[key] = float(value)
                else:
                    result[key] = int(value)
            except:
                result[key] = value
                
        # Match "key": true/false patterns (boolean values)
        bool_pattern = r'"([^"]+)"\s*:\s*(true|false)'
        for match in re.finditer(bool_pattern, malformed_json):
            key, value = match.groups()
            result[key] = (value.lower() == 'true')
            
        # If we found any key-value pairs, return them
        if result:
            return result
    except:
        pass
        
    # Strategy 3: Last resort - try to extract any key-value like patterns
    try:
        result = {}
        # Look for patterns like key=value or key: value
        pattern = r'([a-zA-Z0-9_]+)[=:]\s*([a-zA-Z0-9_./\\-]+)'
        for match in re.finditer(pattern, malformed_json):
            key, value = match.groups()
            # Try to convert value to appropriate type
            if value.lower() == 'true':
                result[key] = True
            elif value.lower() == 'false':
                result[key] = False
            elif value.isdigit():
                result[key] = int(value)
            elif re.match(r'^-?\d+\.\d+$', value):
                result[key] = float(value)
            else:
                result[key] = value
        return result
    except:
        # If all strategies fail, return empty dict
        return {}
