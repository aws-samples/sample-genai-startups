#!/usr/bin/env python3
"""Read-only inventory of a Bedrock agent (+ collaborators) -> JSON on stdout.
Flags apiSchema action groups (silently dropped by import).
Usage: inventory_bedrock_agent.py --agent-id ID --region R [--profile P]
       [--version DRAFT] [--redact-instructions]
Output is SENSITIVE: it includes full agent instructions (prompt IP, possibly
embedded secrets/PII). Redirect to a file, keep out of VCS and shared logs;
use --redact-instructions for shareable output.
Note: the collaborator's agentId field name varies across API versions; this falls
back to emitting the raw collaborator summary so nothing is lost — verify and extend."""
import argparse, hashlib, json, sys
import boto3

# Error codes that mean "the call failed", not "there is nothing there".
# These must be surfaced loudly — swallowing them corrupts the topology map.
_LOUD_ERRORS = ("AccessDeniedException", "UnauthorizedOperation",
                "ThrottlingException", "TooManyRequestsException",
                "ExpiredTokenException", "UnrecognizedClientException")

def _err_code(e):
    return getattr(e, "response", {}).get("Error", {}).get("Code", "")

def client(region, profile):
    sess = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return sess.client("bedrock-agent", region_name=region)

def action_groups(c, aid, ver):
    out = []
    try:
        summaries = c.list_agent_action_groups(
            agentId=aid, agentVersion=ver).get("actionGroupSummaries", [])
    except Exception as e:
        if _err_code(e) in _LOUD_ERRORS:
            print(f"WARN {_err_code(e)} on list_agent_action_groups({aid}) — "
                  f"action groups may be missing from this map", file=sys.stderr)
        return [{"error": f"list_agent_action_groups: {e}"}]
    for s in summaries:
        try:
            ag = c.get_agent_action_group(agentId=aid, agentVersion=ver,
                actionGroupId=s["actionGroupId"])["agentActionGroup"]
        except Exception as e:
            out.append({"name": s.get("actionGroupName"), "error": str(e)}); continue
        kind = ("apiSchema" if ag.get("apiSchema")
                else "functionSchema" if ag.get("functionSchema") else "unknown")
        out.append({"name": ag.get("actionGroupName"), "schemaType": kind,
                    "executor": ag.get("actionGroupExecutor"),
                    "droppedByImport": kind == "apiSchema"})
    return out

def collaborators(c, aid, ver):
    """Returns (summaries, error). Non-supervisor agents commonly raise a
    ValidationException here — expected, means "no collaborators" (error=None).
    Auth/throttle failures are NOT silent: they would make a real multi-agent
    topology look like a single agent, so they're recorded and warned."""
    try:
        return (c.list_agent_collaborators(
            agentId=aid, agentVersion=ver).get("agentCollaboratorSummaries", []),
            None)
    except Exception as e:
        if _err_code(e) in _LOUD_ERRORS:
            msg = f"list_agent_collaborators: {e}"
            print(f"WARN {_err_code(e)} on list_agent_collaborators({aid}) — "
                  f"collaborator topology may be incomplete; fix credentials/"
                  f"throttling and re-run before trusting this map", file=sys.stderr)
            return [], msg
        return [], None

def collab_ref(col):
    """Resolve a collaborator summary to (agentId, aliasId). The real collaborator
    agent id is in agentDescriptor.aliasArn (.../agent-alias/<AGENT_ID>/<ALIAS_ID>) —
    NOT collaboratorId (an association id) and NOT agentId (the supervisor's id)."""
    arn = (col.get("agentDescriptor") or {}).get("aliasArn", "")
    if "agent-alias/" in arn:
        tail = arn.split("agent-alias/", 1)[1].split("/")
        if len(tail) >= 2:
            return tail[0], tail[1]
    return None, None

def dump(c, aid, ver, seen, redact=False):
    if not aid or aid in seen:
        return {"agentId": aid, "note": "missing id or already captured"}
    seen.add(aid)
    try:
        agent = c.get_agent(agentId=aid)["agent"]
    except Exception as e:
        return {"agentId": aid, "error": str(e)}
    instr = agent.get("instruction")
    if redact and instr:
        instr = (f"<redacted len={len(instr)} "
                 f"sha256={hashlib.sha256(instr.encode()).hexdigest()[:12]}>")
    node = {"agentId": aid, "name": agent.get("agentName"),
            "status": agent.get("agentStatus"), "model": agent.get("foundationModel"),
            "instruction": instr,
            "actionGroups": action_groups(c, aid, ver),
            "knowledgeBases": _safe(c, "list_agent_knowledge_bases", aid, ver,
                                    "agentKnowledgeBaseSummaries"),
            "collaborators": []}
    cols, col_err = collaborators(c, aid, ver)
    if col_err:
        node["collaboratorsError"] = col_err
    for col in cols:
        sub, alias = collab_ref(col)
        child = dump(c, sub, ver, seen, redact) if sub else {"unresolved": col}
        child["collaboratorName"] = col.get("collaboratorName")
        child["collaboratorAliasId"] = alias
        child["collaborationInstruction"] = col.get("collaborationInstruction")
        node["collaborators"].append(child)
    return node

def _safe(c, method, aid, ver, key):
    try:
        return getattr(c, method)(agentId=aid, agentVersion=ver).get(key, [])
    except Exception as e:
        if _err_code(e) in _LOUD_ERRORS:
            print(f"WARN {_err_code(e)} on {method}({aid})", file=sys.stderr)
        return [{"error": f"{method}: {e}"}]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--agent-id", required=True)
    p.add_argument("--region", required=True)  # no silent default: wrong region = empty inventory
    p.add_argument("--profile")
    p.add_argument("--version", default="DRAFT")
    p.add_argument("--redact-instructions", action="store_true",
                   help="replace instruction bodies with <redacted len/sha256> stubs")
    a = p.parse_args()
    c = client(a.region, a.profile)
    inv = {"region": a.region,
           "supervisor": dump(c, a.agent_id, a.version, set(),
                              a.redact_instructions)}
    json.dump(inv, sys.stdout, indent=2, default=str)
    print()
    # surface apiSchema warnings on stderr
    def warn(node):
        for ag in node.get("actionGroups", []):
            if ag.get("droppedByImport"):
                print(f"WARN apiSchema (dropped by import): "
                      f"{node.get('name')}/{ag.get('name')}", file=sys.stderr)
        for col in node.get("collaborators", []):
            if isinstance(col, dict): warn(col)
    warn(inv["supervisor"])

if __name__ == "__main__":
    main()
