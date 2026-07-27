"""Managed AWS Bedrock AgentCore Harness runner -- the promotion path.

The whole portability claim of this demo is "a harness is a config object, not
bespoke code: run it locally for fast/cheap iteration, then promote the SAME
config to a managed runtime with no logic change." This module realizes the
second half. It takes the identical `HarnessConfig` the local Strands executor
uses and runs it on a managed AgentCore Harness, whose microVM runs the same
Strands agent loop under the hood.

Same config, different runner:
  * LocalHarnessExecutor (harness.py) -- Strands SDK in this process. Default;
    no IAM/deploy; used to validate and tune the gap and generate replay traces.
  * AgentCoreHarnessRunner (here)      -- managed CreateHarness + InvokeHarness.
    The "inspect the real trace in AgentCore Observability" credibility path.

It preserves the run_turn(cfg, messages) -> Move seam, so it is a drop-in for
the local executor in negotiate.py / validate.py / server.py.

What is faithful vs. what differs (stated honestly):
  * The config payloads come straight from HarnessConfig.to_create_harness_kwargs()
    / to_invoke_harness_kwargs(), so model, system prompt, tool *specs*,
    truncation, and iteration caps are identical to the local run.
  * GOOD's commit/validate gate is CLIENT-SIDE orchestration that wraps the
    invoke call -- it works identically here (it re-invokes with the rejection
    reason), which is exactly why GOOD is described as a "code-based agent".
  * ONE real difference: in the managed runtime the inline tools execute inside
    the microVM, not via the client-side INLINE_TOOLS Python impls. To run the
    calculator/validator managed, register them as the harness's own tools
    (inline function code, or an AgentCore Gateway / MCP server). This runner
    therefore reflects the managed model's *own* tool execution; the local
    executor is the one that guarantees the client-side deterministic tools.

Requires: a deployed harness (or create one via ensure_harness) + an execution
role ARN with Bedrock access. boto3 with the GA bedrock-agentcore /
bedrock-agentcore-control clients.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Dict, List, Optional

import boto3

from bazaar80.harness import REGION, HarnessConfig, Move
from bazaar80.tools import parse_move

# Data-plane / control-plane client names (GA, verified against the API ref).
CONTROL_PLANE = "bedrock-agentcore-control"
DATA_PLANE = "bedrock-agentcore"


class AgentCoreHarnessRunner:
    """Runs a HarnessConfig on a managed AgentCore Harness via InvokeHarness.

    Pass an existing `harness_arn` to invoke a harness someone already deployed,
    or call `ensure_harness(cfg, ...)` once to create one from a config and reuse
    the returned ARN across turns.
    """

    def __init__(self, harness_arn: Optional[str] = None, *, region: str = REGION):
        self._region = region
        self._harness_arn = harness_arn
        # Lazily created so importing this module never requires the service.
        self._control = None
        self._data = None
        # One stable session id per runner instance (must be >=33 chars; a UUID
        # hex is 32, so we prefix it). The managed harness keys its server-side
        # memory off this, mirroring a single negotiation's rolling context.
        self._session_id = "bazaar80-" + uuid.uuid4().hex

    # --- clients -------------------------------------------------------------- #

    @property
    def control(self):
        if self._control is None:
            self._control = boto3.client(CONTROL_PLANE, region_name=self._region)
        return self._control

    @property
    def data(self):
        if self._data is None:
            self._data = boto3.client(DATA_PLANE, region_name=self._region)
        return self._data

    # --- one-time provisioning ------------------------------------------------ #

    def ensure_harness(self, cfg: HarnessConfig, *, harness_name: str,
                       execution_role_arn: str, poll_seconds: float = 5.0,
                       timeout_seconds: float = 300.0) -> str:
        """Create a managed harness from `cfg` and block until it is READY.

        Returns the harness ARN (also cached on the runner for run_turn). Uses
        the SAME payload the config emits for the local path -- proving the
        config is portable, not rewritten."""
        kwargs = cfg.to_create_harness_kwargs(
            harness_name=harness_name, execution_role_arn=execution_role_arn)
        created = self.control.create_harness(**kwargs)
        arn = created["harnessArn"]

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            status = self.control.get_harness(harnessArn=arn).get("status")
            if status == "READY":
                self._harness_arn = arn
                return arn
            if status in ("CREATE_FAILED", "FAILED"):
                raise RuntimeError(f"harness {arn} entered status {status}")
            time.sleep(poll_seconds)
        raise TimeoutError(f"harness {arn} not READY within {timeout_seconds}s")

    # --- the run_turn seam ---------------------------------------------------- #

    def run_turn(self, cfg: HarnessConfig, messages: List[dict]) -> Move:
        """Invoke the managed harness for one turn and adapt the streamed result
        into a Move, applying GOOD's client-side validate gate around it.

        Mirrors LocalHarnessExecutor.run_turn so it is a drop-in replacement."""
        if not self._harness_arn:
            raise RuntimeError(
                "no harness_arn set -- pass one to the constructor or call "
                "ensure_harness(cfg, harness_name=..., execution_role_arn=...) first")

        agg_usage = {"inputTokens": 0, "outputTokens": 0}
        final_text, usage = self._invoke(cfg, messages)
        agg_usage["inputTokens"] += usage["inputTokens"]
        agg_usage["outputTokens"] += usage["outputTokens"]

        # GOOD harness: the same client-side commit/validate gate as the local
        # executor. A config-based managed harness can't reject its own output;
        # this code-based wrapper re-invokes with the rejection reason.
        validator_bounces = 0
        if cfg.validate_gate:
            from bazaar80.harness import LocalHarnessExecutor  # reuse the gate predicate
            for _attempt in range(3):
                need_fix, reason = LocalHarnessExecutor._gate_check(final_text, cfg.role)
                if not need_fix:
                    break
                validator_bounces += 1
                fix_msgs = messages + [
                    {"role": "assistant", "content": [{"text": final_text or "(no output)"}]},
                    {"role": "user", "content": [{"text":
                        f"VALIDATOR REJECTED that offer: {reason}. Choose a LEGAL, "
                        "non-self-harming deal and reply with ONLY the JSON move "
                        "object, nothing else."}]},
                ]
                final_text, usage = self._invoke(cfg, fix_msgs)
                agg_usage["inputTokens"] += usage["inputTokens"]
                agg_usage["outputTokens"] += usage["outputTokens"]

        action, deal, message, parse_ok = parse_move(final_text)
        return Move(
            action=action, deal=deal, message=message, parse_ok=parse_ok,
            invalid=not parse_ok, scratchpad="", tool_calls=[],
            validator_bounces=validator_bounces, raw_text=final_text,
            usage=agg_usage, cost_usd=0.0,   # managed billing is out of band
        )

    # --- invoke + SSE consumption -------------------------------------------- #

    def _invoke(self, cfg: HarnessConfig, messages: List[dict]) -> tuple[str, Dict[str, int]]:
        """Call InvokeHarness and accumulate the streamed response.

        InvokeHarness is streaming-only: iterate response['stream'], concatenate
        contentBlockDelta text, and read final usage from the metadata event."""
        kwargs = cfg.to_invoke_harness_kwargs(
            harness_arn=self._harness_arn, session_id=self._session_id,
            messages=messages)
        # truncation/executionRole are create-time only; the emitter already omits
        # them from invoke kwargs. maxTokens here is the per-iteration cap.
        resp = self.data.invoke_harness(**kwargs)

        text_parts: List[str] = []
        usage = {"inputTokens": 0, "outputTokens": 0}
        for event in resp.get("stream", []):
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                if "text" in delta:
                    text_parts.append(delta["text"])
            elif "metadata" in event:
                u = event["metadata"].get("usage", {})
                usage["inputTokens"] = u.get("inputTokens", 0)
                usage["outputTokens"] = u.get("outputTokens", 0)
        return "".join(text_parts).strip(), usage


if __name__ == "__main__":
    # Smoke doc: this path needs a deployed harness + exec role. Example wiring:
    #
    #   from bazaar80.harness import good_harness, raw_harness
    #   from bazaar80.agentcore_runner import AgentCoreHarnessRunner
    #   from bazaar80.negotiate import negotiate
    #   runner = AgentCoreHarnessRunner()
    #   runner.ensure_harness(good_harness("seller"),
    #                         harness_name="Bazaar80SellerGood",
    #                         execution_role_arn="arn:aws:iam::<acct>:role/<role>")
    #   # negotiate() takes any object with run_turn(cfg, messages) -> Move:
    #   result = negotiate(good_harness("seller"), raw_harness("buyer"),
    #                      executor=runner, max_rounds=5)
    print(__doc__)
