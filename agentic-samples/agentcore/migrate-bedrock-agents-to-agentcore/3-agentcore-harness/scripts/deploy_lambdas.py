"""Zip and deploy the 3 Lambda tool backends via boto3.

Each Lambda is single-file (app.py), so the zip is built in-memory. Creates
or updates the function idempotently and stores ARNs in state.json.
"""
import io
import time
import zipfile
from pathlib import Path

import boto3

from _state import (
    LAMBDA_DIR,
    REGION,
    TOOLS,
    load_state,
    save_state,
)


def zip_dir(src: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                zf.write(f, arcname=f.relative_to(src))
    return buf.getvalue()


def ensure_function(lam, name: str, zip_bytes: bytes, role_arn: str) -> str:
    try:
        lam.get_function(FunctionName=name)
        resp = lam.update_function_code(FunctionName=name, ZipFile=zip_bytes)
        action = "updated"
    except lam.exceptions.ResourceNotFoundException:
        resp = lam.create_function(
            FunctionName=name,
            Runtime="python3.12",
            Role=role_arn,
            Handler="app.lambda_handler",
            Code={"ZipFile": zip_bytes},
            Timeout=30,
        )
        action = "created"

    # Wait for the function to reach Active state.
    waiter = lam.get_waiter("function_active_v2")
    waiter.wait(FunctionName=name)

    arn = resp["FunctionArn"]
    print(f"  {action} {name}: {arn}")
    return arn


def main():
    state = load_state()
    role_arn = state.get("lambda_role_arn")
    if not role_arn:
        raise SystemExit("lambda_role_arn missing — run setup_iam.py first.")

    lam = boto3.client("lambda", region_name=REGION)
    arns = {}
    print("Deploying Lambdas...")
    for tool in TOOLS:
        zip_bytes = zip_dir(LAMBDA_DIR / tool)
        fn_name = f"PrivateAviationHarness-{tool}"
        arns[tool] = ensure_function(lam, fn_name, zip_bytes, role_arn)

    state["lambda_arns"] = arns
    save_state(state)
    print("Done.")


if __name__ == "__main__":
    main()
