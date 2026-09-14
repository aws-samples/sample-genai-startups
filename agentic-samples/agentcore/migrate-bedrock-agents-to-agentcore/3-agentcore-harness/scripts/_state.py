"""Shared state passed between the Lambda deploy scripts.

Only the Lambda tooling runs under boto3 — the Gateway, Harness, and
invocation paths go through the AgentCore CLI (see the project Makefile).
The CLI maintains its own deployed-state file under agentcore/.cli/.
"""
import json
import os
from pathlib import Path

REGION = os.environ.get("AWS_REGION", "us-east-1")

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "config" / "state.json"
LAMBDA_DIR = REPO_ROOT / "lambda_functions"

LAMBDA_ROLE_NAME = "PrivateAviationHarness-LambdaRole"
LAMBDA_FUNCTION_PREFIX = "PrivateAviationHarness"

TOOLS = ("get_owner_info", "get_passengers", "book_reservation")


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))
