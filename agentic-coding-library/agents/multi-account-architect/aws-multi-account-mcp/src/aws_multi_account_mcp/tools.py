import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import boto3

STATE_FILE = Path.cwd() / ".migration-state.json"

ALLOWED_REPORT_DIR = os.getcwd()
SENSITIVE_EXTENSIONS = ('.json', '.sh', '.py', '.env', '.pem')
MAX_LIMIT = 500


# ---------------------------------------------------------------------------
# Workload Discovery
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _tagging_client():
    return boto3.client("resourcegroupstaggingapi")


@lru_cache(maxsize=1)
def _ec2_client():
    return boto3.client("ec2")


def audit_workloads(
    tag_key: Optional[str] = "Environment",
    name_prefixes: Optional[str] = "prod,dev,staging,shared",
    limit: int = 200,
) -> list[dict]:
    """
    Scan the current AWS account and categorize resources by tags and naming
    conventions to propose an OU split (e.g. Production vs Development).

    Args:
        tag_key: Tag key used to classify resources (e.g. 'Environment', 'Stage') [server-side]
        name_prefixes: Comma-separated prefixes to detect in resource names/IDs
                       (e.g. 'prod,dev,staging'). Used for client-side classification.
        limit: Max resources to return (default: 200)

    Returns:
        List of resources with id, type, region, tags, and suggested_ou fields.
    """
    limit = min(limit, MAX_LIMIT)
    prefixes = [p.strip().lower() for p in (name_prefixes or "").split(",") if p.strip()]
    paginator = _tagging_client().get_paginator("get_resources")
    resources = []

    for page in paginator.paginate(ResourcesPerPage=100):
        for r in page["ResourceTagMappingList"]:
            arn = r["ResourceARN"]
            tags = {t["Key"]: t["Value"] for t in r.get("Tags", [])}
            suggested_ou = _classify(arn, tags, tag_key, prefixes)
            resources.append({
                "arn": arn,
                "type": arn.split(":")[2] if len(arn.split(":")) > 2 else "unknown",
                "tags": tags,
                "suggested_ou": suggested_ou,
            })
            if len(resources) >= limit:
                break
        if len(resources) >= limit:
            break

    return resources


def _classify(arn: str, tags: dict, tag_key: str, prefixes: list[str]) -> str:
    """Classify a resource into a suggested OU based on tags and name prefixes."""
    env = tags.get(tag_key, "").lower()
    if env in ("prod", "production"):
        return "Production"
    if env in ("dev", "development", "staging", "test"):
        return "Development"

    name = arn.lower()
    for prefix in prefixes:
        safe_prefix = re.escape(prefix)
        if prefix in ("prod", "production") and re.search(rf"[:/\-_]{safe_prefix}[:/\-_]|{safe_prefix}[-_]", name):
            return "Production"
        if prefix in ("dev", "development", "staging", "test") and re.search(rf"[:/\-_]{safe_prefix}[:/\-_]|{safe_prefix}[-_]", name):
            return "Development"

    return "Unclassified"


# ---------------------------------------------------------------------------
# Dependency Pre-flight Check
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _iam_client():
    return boto3.client("iam")


@lru_cache(maxsize=1)
def _sts_client():
    return boto3.client("sts")


def check_dependencies(limit: int = 100) -> list[dict]:
    """
    Scan IAM roles and their inline/attached policies for hardcoded AWS Account
    IDs or ARNs that will break when resources move to a new account.

    Args:
        limit: Max IAM roles to inspect (default: 100)

    Returns:
        List of findings with role_name, policy_name, hardcoded_refs, and
        remediation_hint fields.
    """
    limit = min(limit, MAX_LIMIT)
    current_account = _sts_client().get_caller_identity()["Account"]
    findings = []
    paginator = _iam_client().get_paginator("list_roles")
    count = 0

    for page in paginator.paginate():
        for role in page["Roles"]:
            if count >= limit:
                break
            count += 1
            role_name = role["RoleName"]

            # Inline policies
            inline = _iam_client().list_role_policies(RoleName=role_name)["PolicyNames"]
            for pname in inline:
                doc = _iam_client().get_role_policy(RoleName=role_name, PolicyName=pname)["PolicyDocument"]
                refs = _find_hardcoded_refs(json.dumps(doc), current_account)
                if refs:
                    findings.append({
                        "role_name": role_name,
                        "policy_name": pname,
                        "policy_type": "inline",
                        "hardcoded_refs": refs,
                        "remediation_hint": "Replace hardcoded account IDs with ${AWS::AccountId} (CFN) or data.aws_caller_identity (TF)",
                    })

            # Attached managed policies
            attached = _iam_client().list_attached_role_policies(RoleName=role_name)["AttachedPolicies"]
            for p in attached:
                version_id = _iam_client().get_policy(PolicyArn=p["PolicyArn"])["Policy"]["DefaultVersionId"]
                doc = _iam_client().get_policy_version(PolicyArn=p["PolicyArn"], VersionId=version_id)["PolicyVersion"]["Document"]
                refs = _find_hardcoded_refs(json.dumps(doc), current_account)
                if refs:
                    findings.append({
                        "role_name": role_name,
                        "policy_name": p["PolicyName"],
                        "policy_type": "managed",
                        "hardcoded_refs": refs,
                        "remediation_hint": "Replace hardcoded account IDs with ${AWS::AccountId} (CFN) or data.aws_caller_identity (TF)",
                    })

        if count >= limit:
            break

    return findings


def _find_hardcoded_refs(policy_json: str, account_id: str) -> list[str]:
    """Extract hardcoded account ID occurrences from a policy document string."""
    pattern = rf'arn:aws:[^"]*:{account_id}:[^"]*'
    return list(set(re.findall(pattern, policy_json)))


# ---------------------------------------------------------------------------
# Migration State (persistent checklist)
# ---------------------------------------------------------------------------

def get_migration_state() -> dict:
    """
    Read the current migration checklist state from disk.

    Returns:
        Dict with 'steps' (list of step objects with name, status, notes)
        and 'last_updated' fields. Returns empty state if no file exists.
    """
    if not STATE_FILE.exists():
        return {"steps": [], "last_updated": None}
    return json.loads(STATE_FILE.read_text())


def update_migration_state(
    step_name: str,
    status: str,
    notes: Optional[str] = None,
) -> dict:
    """
    Create or update a migration checklist step and persist it to disk.

    Args:
        step_name: Short identifier for the step (e.g. 'create_organization',
                   'enable_sso', 'move_prod_account')
        status: Step status — one of 'pending', 'in_progress', 'done', 'blocked'
        notes: Optional free-text notes or next action for this step

    Returns:
        The full updated migration state dict.
    """
    from datetime import datetime, timezone
    state = get_migration_state()
    steps = state.get("steps", [])

    existing = next((s for s in steps if s["name"] == step_name), None)
    if existing:
        existing["status"] = status
        if notes is not None:
            existing["notes"] = notes
    else:
        steps.append({"name": step_name, "status": status, "notes": notes or ""})

    state = {"steps": steps, "last_updated": datetime.now(timezone.utc).isoformat()}
    STATE_FILE.write_text(json.dumps(state, indent=2))
    return state


# ---------------------------------------------------------------------------
# Migration Report (Markdown with Mermaid diagrams)
# ---------------------------------------------------------------------------

def write_migration_report(
    report_path: str,
    source_account_id: str,
    source_resources: list[dict],
    target_ous: list[dict],
) -> dict:
    """
    Write or overwrite a MIGRATION.md file containing:
    - A task checklist reflecting current migration state
    - A Mermaid diagram of the original single-account architecture
    - A Mermaid diagram of the target multi-account Organization structure

    Call this after every update_migration_state call to keep the report current.

    Args:
        report_path: Absolute or relative path where MIGRATION.md should be written
        source_account_id: The current (source) AWS account ID
        source_resources: List of resource dicts from audit_workloads (used to build source diagram)
        target_ous: List of OU dicts, each with 'name' and 'accounts' (list of account name strings)
                    e.g. [{"name": "Production", "accounts": ["prod-workloads"]}, ...]

    Returns:
        Dict with 'path' and 'written' (bool).
    """
    state = get_migration_state()
    steps = state.get("steps", [])

    # Task checklist
    checklist_lines = ["## Migration Checklist", ""]
    status_icon = {"done": "x", "in_progress": "/", "blocked": "!", "pending": " "}
    for step in steps:
        icon = status_icon.get(step["status"], " ")
        note = f" — {step['notes']}" if step.get("notes") else ""
        checklist_lines.append(f"- [{icon}] **{step['name']}** `{step['status']}`{note}")
    if not steps:
        checklist_lines.append("_No steps recorded yet._")

    # Source architecture diagram — group resources by type
    type_counts: dict[str, int] = {}
    for r in source_resources:
        t = r.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    source_nodes = "\n    ".join(
        f'{t.replace("-", "_")}["{t} x{count}"]'
        for t, count in list(type_counts.items())[:10]  # cap at 10 node types
    )
    source_diagram = f"""## Current Architecture

```mermaid
graph TD
    Account["AWS Account\\n{source_account_id}"]
    {source_nodes}
    Account --> {" & Account --> ".join(t.replace("-", "_") for t in list(type_counts.keys())[:10])}
```"""

    # Target architecture diagram
    ou_nodes = []
    ou_edges = []
    for ou in target_ous:
        ou_id = ou["name"].replace(" ", "_")
        ou_nodes.append(f'    {ou_id}["{ou["name"]} OU"]')
        ou_edges.append(f"    Root --> {ou_id}")
        for acc in ou.get("accounts", []):
            acc_id = acc.replace(" ", "_").replace("-", "_")
            ou_nodes.append(f'    {acc_id}["{acc}"]')
            ou_edges.append(f"    {ou_id} --> {acc_id}")

    target_diagram = f"""## Target Architecture

```mermaid
graph TD
    Root["AWS Organization Root"]
    Mgmt["Management Account"]
    LogArchive["Log Archive Account"]
    Security["Security Tooling Account"]
    Root --> Mgmt
    Root --> LogArchive
    Root --> Security
{chr(10).join(ou_nodes)}
{chr(10).join(ou_edges)}
```"""

    last_updated = state.get("last_updated", "never")
    content = f"""# Migration Plan

_Last updated: {last_updated}_

{chr(10).join(checklist_lines)}

---

{source_diagram}

---

{target_diagram}
"""

    # Validate report path stays within allowed directory
    resolved = os.path.realpath(report_path)
    allowed = os.path.realpath(ALLOWED_REPORT_DIR)
    if not resolved.startswith(allowed + os.sep) and resolved != allowed:
        return {"error": f"Path must be within {ALLOWED_REPORT_DIR}", "written": False}
    if any(resolved.endswith(ext) for ext in SENSITIVE_EXTENSIONS):
        return {"error": "Cannot write to sensitive file types", "written": False}

    Path(report_path).write_text(content)
    return {"path": report_path, "written": True}
