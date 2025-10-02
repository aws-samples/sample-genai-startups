import json
import re

def parse_config(config_str):
    """Parse tool configuration with recovery for malformed JSON."""
    print(f"[MCP_DEBUG] Parsing config string: {config_str[:200]}..." if len(str(config_str)) > 200 else f"[MCP_DEBUG] Parsing config string: {config_str}")
    
    if not config_str:
        print(f"[MCP_DEBUG] Empty config string, returning empty dict")
        return {}
    
    try:
        result = json.loads(config_str)
        print(f"[MCP_DEBUG] Successfully parsed JSON config: {result}")
        return result
    except Exception as e:
        print(f"[MCP_DEBUG] JSON parsing failed: {str(e)}, attempting recovery")
        recovered = _recover_json(config_str)
        print(f"[MCP_DEBUG] Recovered config: {recovered}")
        return recovered

def locate_config(config_dict):
    """Locate MCP configuration in nested JSON structure."""
    print(f"[MCP_DEBUG] Locating config in: {config_dict}")
    
    if not isinstance(config_dict, dict):
        print(f"[MCP_DEBUG] Config is not a dict: {type(config_dict)}")
        return None, None, None, None
    
    # Check current level first
    if 'command' in config_dict:
        result = (
            config_dict['command'],
            config_dict.get('args', []),
            config_dict.get('env', {}),
            config_dict.get('disabled_tools', [])
        )
        print(f"[MCP_DEBUG] Found command at current level: {result}")
        return result
    
    # Recursively search nested dictionaries
    for key, value in config_dict.items():
        print(f"[MCP_DEBUG] Checking nested key: {key}, value type: {type(value)}")
        if isinstance(value, dict):
            cmd, args, env, disabled = locate_config(value)
            if cmd:
                print(f"[MCP_DEBUG] Found command in nested key {key}: {cmd}")
                return cmd, args, env, disabled
    
    print(f"[MCP_DEBUG] No command found in config")
    return None, None, None, None

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