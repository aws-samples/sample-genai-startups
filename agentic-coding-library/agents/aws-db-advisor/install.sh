#!/usr/bin/env bash
# Install aws-db-advisor as a Kiro agent (default), Kiro Power, or Claude Code Skill.
set -euo pipefail

AGENT_NAME="aws-db-advisor"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTEXT_DIR="$SOURCE_DIR/.kiro/context/$AGENT_NAME"

MCP_SERVER_NAME="aws-knowledge-mcp-server"
MCP_SERVER_COMMAND="npx"
MCP_SERVER_ARGS='["mcp-remote@0.1.38", "https://knowledge-mcp.global.api.aws"]'

usage() {
  cat <<EOF
Usage: $0 [MODE] [OPTIONS]

Modes:
  agent   Install as Kiro agent (default)
  power   Install as Kiro Power
  claude  Install as Claude Code Skill
  all     Install all three targets
  uninstall         Uninstall all targets
  uninstall-agent   Uninstall Kiro agent only
  uninstall-power   Uninstall Kiro Power only
  uninstall-claude  Uninstall Claude Code Skill only

Options:
  --agent NAME   Integrate into an existing Kiro agent instead of creating
                 a new one. Merges context files, resources, MCP servers,
                 and tools into the target agent's configuration.
EOF
  exit 1
}

# --- Kiro Agent ---

install_agent() {
  local TARGET_DIR="$HOME/.kiro/agents/$AGENT_NAME"

  echo "Installing Kiro agent..."

  if [ -d "$TARGET_DIR" ]; then
    rm -rf "${TARGET_DIR}.bak"
    mv "$TARGET_DIR" "${TARGET_DIR}.bak"
    echo "  backed up existing installation"
  fi

  mkdir -p "$TARGET_DIR/.kiro/agents"
  mkdir -p "$TARGET_DIR/.kiro/context/$AGENT_NAME"

  cp "$SOURCE_DIR/.kiro/agents/$AGENT_NAME.json" "$TARGET_DIR/.kiro/agents/$AGENT_NAME.json"

  for f in "$CONTEXT_DIR"/*.md; do
    cp "$f" "$TARGET_DIR/.kiro/context/$AGENT_NAME/"
  done

  cp "$SOURCE_DIR/POWER.md" "$TARGET_DIR/POWER.md"
  cp "$SOURCE_DIR/POWER.md" "$TARGET_DIR/.kiro/agents/POWER.md"
  cp "$SOURCE_DIR/README.md" "$TARGET_DIR/README.md"
  [ -f "$SOURCE_DIR/DESIGN.md" ] && cp "$SOURCE_DIR/DESIGN.md" "$TARGET_DIR/DESIGN.md"

  if [ -d "$SOURCE_DIR/tests" ]; then
    cp -r "$SOURCE_DIR/tests" "$TARGET_DIR/tests"
  fi

  ln -sf "$TARGET_DIR/.kiro/agents/$AGENT_NAME.json" "$HOME/.kiro/agents/$AGENT_NAME.json"

  echo "  installed at: $TARGET_DIR"
  echo "  launch with: kiro-cli chat --agent $AGENT_NAME"
}

uninstall_agent() {
  local TARGET_DIR="$HOME/.kiro/agents/$AGENT_NAME"

  echo "Uninstalling Kiro agent..."

  rm -f "$HOME/.kiro/agents/$AGENT_NAME.json"

  if [ -d "$TARGET_DIR" ]; then
    rm -rf "$TARGET_DIR"
    echo "  removed: $TARGET_DIR"
  else
    echo "  not found (skipped)"
  fi
}

# --- Integrate into existing agent ---

integrate_agent() {
  local TARGET_AGENT="$1"
  local TARGET_JSON=""

  # Try multiple resolution strategies:
  # 1. Direct path (if user passed a file path)
  # 2. ~/.kiro/agents/<name>.json (symlink or file)
  # 3. ~/.kiro/agents/agent_config.json (if name matches its "name" field)
  if [ -f "$TARGET_AGENT" ]; then
    TARGET_JSON="$TARGET_AGENT"
  elif [ -f "$HOME/.kiro/agents/$TARGET_AGENT.json" ]; then
    TARGET_JSON="$HOME/.kiro/agents/$TARGET_AGENT.json"
  elif [ -f "$HOME/.kiro/agents/agent_config.json" ]; then
    # Check if the agent_config.json has a matching name
    local CONFIG_NAME
    CONFIG_NAME=$(python3 -c "
import json
with open('$HOME/.kiro/agents/agent_config.json') as f:
    print(json.load(f).get('name', ''))
")
    if [ "$CONFIG_NAME" = "$TARGET_AGENT" ] || [ "$TARGET_AGENT" = "agent_config" ]; then
      TARGET_JSON="$HOME/.kiro/agents/agent_config.json"
    fi
  fi

  # Resolve symlinks
  if [ -n "$TARGET_JSON" ] && [ -L "$TARGET_JSON" ]; then
    TARGET_JSON="$(readlink "$TARGET_JSON")"
  fi

  if [ -z "$TARGET_JSON" ] || [ ! -f "$TARGET_JSON" ]; then
    echo "ERROR: Agent '$TARGET_AGENT' not found."
    echo "  Tried: ~/.kiro/agents/$TARGET_AGENT.json"
    echo "         ~/.kiro/agents/agent_config.json (name field match)"
    echo "         Direct path"
    exit 1
  fi

  echo "Integrating $AGENT_NAME into: $TARGET_JSON"

  # Determine context target — use ~/.kiro/context/ for agents using glob resources
  local TARGET_CONTEXT_DIR="$HOME/.kiro/context/$AGENT_NAME"
  mkdir -p "$TARGET_CONTEXT_DIR"

  # Copy context files
  for f in "$CONTEXT_DIR"/*.md; do
    cp "$f" "$TARGET_CONTEXT_DIR/"
  done
  echo "  copied context files to: $TARGET_CONTEXT_DIR"

  # Merge JSON: resources, mcpServers, tools, allowedTools
  python3 -c "
import json, sys

target_path = '$TARGET_JSON'
source_path = '$SOURCE_DIR/.kiro/agents/$AGENT_NAME.json'

with open(target_path) as f:
    target = json.load(f)
with open(source_path) as f:
    source = json.load(f)

# Determine resource style: glob-based or individual
target_resources = target.get('resources', [])
uses_globs = any('*' in r for r in target_resources)

if uses_globs:
    # Check if a glob already covers our context dir
    context_glob = 'file://~/.kiro/context/$AGENT_NAME/*.md'
    if context_glob not in target_resources:
        target_resources.append(context_glob)
        print(f'  added resource glob: {context_glob}')
    else:
        print(f'  resource glob already present')
else:
    # Add individual resource entries
    target_set = set(target_resources)
    for r in source.get('resources', []):
        target_set.add(r)
    target_resources = sorted(target_set)
    print(f'  merged {len(source.get(\"resources\", []))} individual resources')

target['resources'] = target_resources

# Merge mcpServers (don't overwrite existing)
if 'mcpServers' not in target:
    target['mcpServers'] = {}
for name, config in source.get('mcpServers', {}).items():
    if name not in target['mcpServers']:
        target['mcpServers'][name] = config
        print(f'  added MCP server: {name}')
    else:
        print(f'  MCP server already present: {name}')

# Merge tools (deduplicate)
target_tools = list(target.get('tools', []))
for t in source.get('tools', []):
    if t not in target_tools:
        target_tools.append(t)
target['tools'] = target_tools

# Merge allowedTools (deduplicate)
target_allowed = list(target.get('allowedTools', []))
for t in source.get('allowedTools', []):
    if t not in target_allowed:
        target_allowed.append(t)
target['allowedTools'] = target_allowed

with open(target_path, 'w') as f:
    json.dump(target, f, indent=2)

print(f'  target now has {len(target[\"resources\"])} resources')
"

  echo "  integration complete"
}

# --- Kiro Power ---

install_power() {
  local INSTALL_DIR="$HOME/.kiro/powers/installed/$AGENT_NAME"

  echo "Installing Kiro Power..."

  rm -rf "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR/references"

  cp "$SOURCE_DIR/POWER.md" "$INSTALL_DIR/"

  for f in "$CONTEXT_DIR"/*.md; do
    cp "$f" "$INSTALL_DIR/references/"
  done

  # Kiro expects steering/ for powers — symlink to references/
  ln -sf references "$INSTALL_DIR/steering"

  # Register in installed.json (create if missing)
  local INSTALLED_JSON="$HOME/.kiro/powers/installed.json"
  if [ ! -f "$INSTALLED_JSON" ]; then
    mkdir -p "$(dirname "$INSTALLED_JSON")"
    echo '{"installedPowers": []}' > "$INSTALLED_JSON"
  fi
  python3 -c "
import json
with open('$INSTALLED_JSON', 'r') as f:
    data = json.load(f)
powers = data.get('installedPowers', [])
powers = [p for p in powers if p.get('name') != '$AGENT_NAME']
powers.append({'name': '$AGENT_NAME', 'registryId': 'user-added'})
data['installedPowers'] = powers
with open('$INSTALLED_JSON', 'w') as f:
    json.dump(data, f, indent=2)
"
  echo "  registered in installed.json"

  # Add MCP server to Kiro settings
  ensure_mcp_kiro

  echo "  installed at: $INSTALL_DIR"
}

uninstall_power() {
  local INSTALL_DIR="$HOME/.kiro/powers/installed/$AGENT_NAME"

  echo "Uninstalling Kiro Power..."

  if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "  removed: $INSTALL_DIR"
  else
    echo "  not found (skipped)"
  fi

  local INSTALLED_JSON="$HOME/.kiro/powers/installed.json"
  if [ -f "$INSTALLED_JSON" ]; then
    python3 -c "
import json
with open('$INSTALLED_JSON', 'r') as f:
    data = json.load(f)
powers = data.get('installedPowers', [])
powers = [p for p in powers if p.get('name') != '$AGENT_NAME']
data['installedPowers'] = powers
with open('$INSTALLED_JSON', 'w') as f:
    json.dump(data, f, indent=2)
"
    echo "  deregistered from installed.json"
  fi
}

# --- Claude Code Skill ---

install_claude() {
  local COMMANDS_DIR="$HOME/.claude/commands"
  local SKILL_FILE="$COMMANDS_DIR/$AGENT_NAME.md"
  local REFERENCES_DIR="$HOME/.claude/references-$AGENT_NAME"

  echo "Installing Claude Code Skill..."

  mkdir -p "$COMMANDS_DIR"

  rm -rf "$REFERENCES_DIR"
  mkdir -p "$REFERENCES_DIR"

  for f in "$CONTEXT_DIR"/*.md; do
    cp "$f" "$REFERENCES_DIR/"
  done

  # Copy skill file, replacing $REFERENCES_PATH with the absolute path
  sed "s|\\\$REFERENCES_PATH|$REFERENCES_DIR|g" "$SOURCE_DIR/claude/$AGENT_NAME.md" > "$SKILL_FILE"

  # Add MCP server to Claude Code settings
  ensure_mcp_claude

  echo "  skill installed at: $SKILL_FILE"
  echo "  reference files at: $REFERENCES_DIR"
  echo "  invoke with: /aws-db-advisor"
}

uninstall_claude() {
  local SKILL_FILE="$HOME/.claude/commands/$AGENT_NAME.md"
  local REFERENCES_DIR="$HOME/.claude/references-$AGENT_NAME"

  echo "Uninstalling Claude Code Skill..."

  if [ -f "$SKILL_FILE" ]; then
    rm -f "$SKILL_FILE"
    echo "  removed: $SKILL_FILE"
  else
    echo "  not found (skipped)"
  fi

  if [ -d "$REFERENCES_DIR" ]; then
    rm -rf "$REFERENCES_DIR"
    echo "  removed: $REFERENCES_DIR"
  fi
}

# --- MCP server helpers ---

ensure_mcp_kiro() {
  local MCP_SETTINGS="$HOME/.kiro/settings/mcp.json"

  if [ ! -f "$MCP_SETTINGS" ]; then
    mkdir -p "$(dirname "$MCP_SETTINGS")"
    echo '{}' > "$MCP_SETTINGS"
  fi

  local HAS_MCP
  HAS_MCP=$(python3 -c "
import json
with open('$MCP_SETTINGS') as f:
    data = json.load(f)
servers = data.get('mcpServers', {})
power_servers = data.get('powers', {}).get('mcpServers', {})
print('yes' if '$MCP_SERVER_NAME' in servers or '$MCP_SERVER_NAME' in power_servers else 'no')
")

  if [ "$HAS_MCP" = "yes" ]; then
    echo "  $MCP_SERVER_NAME already configured in Kiro"
    return
  fi

  python3 -c "
import json
with open('$MCP_SETTINGS') as f:
    data = json.load(f)
if 'mcpServers' not in data:
    data['mcpServers'] = {}
data['mcpServers']['$MCP_SERVER_NAME'] = {
    'command': '$MCP_SERVER_COMMAND',
    'args': $MCP_SERVER_ARGS,
    'disabled': False,
    'autoApprove': [
        'aws___search_documentation',
        'aws___read_documentation',
        'aws___recommend',
        'aws___retrieve_skill',
        'aws___list_regions',
        'aws___get_regional_availability'
    ]
}
with open('$MCP_SETTINGS', 'w') as f:
    json.dump(data, f, indent=2)
"
  echo "  added $MCP_SERVER_NAME to Kiro MCP settings"
}

ensure_mcp_claude() {
  local SETTINGS_FILE="$HOME/.claude/settings.json"

  if [ ! -f "$SETTINGS_FILE" ]; then
    mkdir -p "$(dirname "$SETTINGS_FILE")"
    echo '{}' > "$SETTINGS_FILE"
  fi

  local HAS_MCP
  HAS_MCP=$(python3 -c "
import json
with open('$SETTINGS_FILE') as f:
    data = json.load(f)
servers = data.get('mcpServers', {})
perms = data.get('permissions', {}).get('allow', [])
found = '$MCP_SERVER_NAME' in servers or any('$MCP_SERVER_NAME' in p for p in perms)
print('yes' if found else 'no')
")

  if [ "$HAS_MCP" = "yes" ]; then
    echo "  $MCP_SERVER_NAME already configured in Claude Code"
    return
  fi

  python3 -c "
import json
with open('$SETTINGS_FILE') as f:
    data = json.load(f)
if 'mcpServers' not in data:
    data['mcpServers'] = {}
data['mcpServers']['$MCP_SERVER_NAME'] = {
    'command': '$MCP_SERVER_COMMAND',
    'args': $MCP_SERVER_ARGS,
    'disabled': False
}
if 'permissions' not in data:
    data['permissions'] = {}
if 'allow' not in data['permissions']:
    data['permissions']['allow'] = []
mcp_tools = [
    'mcp__${MCP_SERVER_NAME}__aws___search_documentation',
    'mcp__${MCP_SERVER_NAME}__aws___read_documentation',
    'mcp__${MCP_SERVER_NAME}__aws___recommend',
    'mcp__${MCP_SERVER_NAME}__aws___retrieve_skill',
    'mcp__${MCP_SERVER_NAME}__aws___list_regions',
    'mcp__${MCP_SERVER_NAME}__aws___get_regional_availability'
]
for tool in mcp_tools:
    if tool not in data['permissions']['allow']:
        data['permissions']['allow'].append(tool)
with open('$SETTINGS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
"
  echo "  added $MCP_SERVER_NAME to Claude Code settings (with auto-approve)"
}

# --- Main ---

echo "=== AWS Database Advisor Installer ==="
echo ""

# Parse arguments
MODE="${1:-agent}"
TARGET_AGENT_NAME=""

shift 2>/dev/null || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      TARGET_AGENT_NAME="${2:-}"
      if [ -z "$TARGET_AGENT_NAME" ]; then
        echo "ERROR: --agent requires a name argument"
        exit 1
      fi
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

case "$MODE" in
  agent)
    if [ -n "$TARGET_AGENT_NAME" ]; then
      integrate_agent "$TARGET_AGENT_NAME"
    else
      install_agent
    fi
    ;;
  power)
    install_power
    ;;
  claude)
    install_claude
    ;;
  all)
    if [ -n "$TARGET_AGENT_NAME" ]; then
      integrate_agent "$TARGET_AGENT_NAME"
    else
      install_agent
    fi
    install_power
    install_claude
    ;;
  uninstall)
    uninstall_agent
    uninstall_power
    uninstall_claude
    ;;
  uninstall-agent)
    uninstall_agent
    ;;
  uninstall-power)
    uninstall_power
    ;;
  uninstall-claude)
    uninstall_claude
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown mode: $MODE"
    echo ""
    usage
    ;;
esac

echo ""
echo "Done."
echo ""
echo "Other install modes available:"
echo "  ./install.sh agent                — Kiro agent (default)"
echo "  ./install.sh agent --agent NAME   — Integrate into existing agent"
echo "  ./install.sh power                — Kiro Power"
echo "  ./install.sh claude               — Claude Code Skill (/aws-db-advisor)"
echo "  ./install.sh all                  — All three targets"
echo "  ./install.sh --help               — Full usage"
