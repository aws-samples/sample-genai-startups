"""Harness-as-config for Bazaar-80.

The whole thesis of the demo is "capability lives at the model x harness
configuration, not the model alone" (Harness-Bench). So a harness here is a
*config object* -- HarnessConfig -- whose fields deliberately mirror AWS
AgentCore's CreateHarness / InvokeHarness API (model, systemPrompt, tools,
truncation, maxIterations). The same config can be:

  * run locally via LocalHarnessExecutor -- the real Strands Agents SDK (the same
    open-source agent loop the managed AgentCore Harness runs in its microVM) --
    fast, no IAM/deploy, used to validate and tune the gap, and
  * promoted to a managed AgentCore Harness via AgentCoreHarnessRunner
    (agentcore_runner.py), which calls the GA CreateHarness / InvokeHarness APIs
    using to_create_harness_kwargs() / to_invoke_harness_kwargs() -- the booth /
    Observability path. Same config, different runner.

Four named configurations form the ladder (no harness -> prebuilt -> engineered):
  RAW     : large model, persona only, no tools, full context, single pass.
  DEFAULT : the prebuilt config-based scaffold -- persona + calculator/validator/
            BATNA tools + multi-iteration loop + framework-default memory, but NO
            task engineering. Isolates "turn the agent framework on".
  GOOD    : DEFAULT + ToM coaching prompt + summarization memory + a code-based
            commit/validate gate (rejects illegal/self-harming offers and
            retries). Isolates "engineer the harness for the task".
  BAD     : large model + over-cautious "guardrail" overlay + NO useful tools +
            tiny sliding-window truncation (drops prior offers -> the agent
            references offers never made: an execution-alignment failure).

The point the audience sees: flip GOOD's harness onto the large model and it
wins; saddle the large model with BAD and it loses to small+GOOD. Same models,
different config.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from strands import Agent, tool
from strands.agent.conversation_manager import (
    NullConversationManager,
    SlidingWindowConversationManager,
    SummarizingConversationManager,
)
from strands.models import BedrockModel
from strands.types.agent import Limits

from bazaar80.game import Deal, bargaining_set, buyer_utility, seller_utility
from bazaar80.prompts import (
    BUYER_PERSONA,
    DEAL_SPACE_BLURB,
    GUARDRAIL_INJECTION,
    GUARDRAIL_MANGLE_RATE,
    NEGOTIATION_SKILL,
    OUTPUT_CONTRACT,
    SELLER_PERSONA,
)
from bazaar80.tools import batna, calc_utility, parse_move, validate_offer

# Default small/large pair (booth framing): a small, ~commodity-priced model with
# a GOOD harness vs a frontier model. Both on Bedrock.
SMALL_MODEL = "us.amazon.nova-2-lite-v1:0"
LARGE_MODEL = "us.anthropic.claude-sonnet-4-6"
REGION = "us-west-2"

# Approximate on-demand Bedrock prices ($ per 1K tokens), for the cost HUD only.
# Marked approximate; not used for billing. The big small-vs-large cost gap is
# itself part of the booth message ("better outcome at a fraction of the cost").
MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    # modelId: (input_per_1k, output_per_1k)
    "us.amazon.nova-2-lite-v1:0": (0.00006, 0.00024),
    "us.anthropic.claude-sonnet-4-6": (0.003, 0.015),
    # legacy/alt pairs kept for easy swapping
    "us.meta.llama3-1-8b-instruct-v1:0": (0.00022, 0.00022),
    "us.meta.llama3-3-70b-instruct-v1:0": (0.00072, 0.00072),
    "us.amazon.nova-lite-v1:0": (0.00006, 0.00024),
}


class HarnessKind(str, Enum):
    GOOD = "good"
    DEFAULT = "default"
    RAW = "raw"
    BAD = "bad"


# --------------------------------------------------------------------------- #
# Inline tools (client-side implementations of the harness's inlineFunction set)
# --------------------------------------------------------------------------- #

def _tool_calc_my_utility(role: str, args: dict) -> str:
    deal = Deal(float(args["unit_price"]), str(args["payment_terms"]).lower())
    return json.dumps({"your_surplus": calc_utility(deal, role), "deal": deal.as_dict()})


def _tool_validate_my_offer(role: str, args: dict) -> str:
    deal = Deal(float(args["unit_price"]), str(args["payment_terms"]).lower())
    ok, reason = validate_offer(deal, role)
    return json.dumps({"valid": ok, "reason": reason, "your_surplus": calc_utility(deal, role)})


def _tool_my_batna(role: str, args: dict) -> str:
    return json.dumps({"walkaway_value": batna(role)})


# name -> (description, JSON input schema, impl(role, args) -> json str)
INLINE_TOOLS: Dict[str, Tuple[str, dict, Callable[[str, dict], str]]] = {
    "calc_my_utility": (
        "Compute YOUR exact surplus for a candidate deal. Use before every offer "
        "so you never miscalculate price x quantity or the cost of a concession.",
        {
            "type": "object",
            "properties": {
                "unit_price": {"type": "number"},
                "payment_terms": {"type": "string", "enum": ["prepaid", "net30", "net60"]},
            },
            "required": ["unit_price", "payment_terms"],
        },
        _tool_calc_my_utility,
    ),
    "validate_my_offer": (
        "Check a candidate deal is legal and not below your walkaway BEFORE sending it. "
        "Returns valid=false with a reason if the offer is illegal or self-harming.",
        {
            "type": "object",
            "properties": {
                "unit_price": {"type": "number"},
                "payment_terms": {"type": "string", "enum": ["prepaid", "net30", "net60"]},
            },
            "required": ["unit_price", "payment_terms"],
        },
        _tool_validate_my_offer,
    ),
    "my_batna": (
        "Look up your walkaway value (the minimum surplus worth accepting).",
        {"type": "object", "properties": {}},
        _tool_my_batna,
    ),
}

GOOD_TOOL_NAMES = ("calc_my_utility", "validate_my_offer", "my_batna")


# --------------------------------------------------------------------------- #
# HarnessConfig (mirrors AgentCore CreateHarness/InvokeHarness fields)
# --------------------------------------------------------------------------- #

@dataclass
class HarnessConfig:
    kind: HarnessKind
    role: str                      # "seller" | "buyer"
    model_id: str
    system_prompt: str
    tool_names: Tuple[str, ...] = ()
    truncation: str = "none"       # "none" | "summarization" | "sliding_window"
    truncation_keep: int = 6       # messages kept (sliding_window) or recent-preserve
    max_iterations: int = 1        # tool-loop iterations allowed within one turn
    max_tokens: int = 600
    temperature: float = 0.4
    guardrail_overlay: bool = False  # BAD harness: cautious overlay + output mangle
    validate_gate: bool = False      # GOOD harness: commit + validator retry loop
    skills: Tuple[str, ...] = ()     # GOOD harness: named negotiation-policy skills
                                     # the agent reasons WITH (mirrors the AgentCore
                                     # CreateHarness `skills` field). The skill TEXT
                                     # is already baked into system_prompt for the
                                     # local run; this records it for portability.

    # --- AgentCore API payload emitters (proves config portability) --------- #

    def _model_block(self) -> dict:
        return {
            "bedrockModelConfig": {
                "modelId": self.model_id,
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            }
        }

    def _tool_blocks(self) -> List[dict]:
        blocks = []
        for name in self.tool_names:
            desc, schema, _impl = INLINE_TOOLS[name]
            blocks.append(
                # NB: the tool TYPE is snake_case `inline_function` per the GA
                # AgentCore API; `inlineFunction` is only the inner config key.
                {"type": "inline_function", "name": name,
                 "config": {"inlineFunction": {"description": desc, "inputSchema": schema}}}
            )
        return blocks

    def _truncation_block(self) -> Optional[dict]:
        if self.truncation == "summarization":
            return {"strategy": "summarization",
                    "config": {"summarization": {"summaryRatio": 0.5,
                                                  "preserveRecentMessages": self.truncation_keep}}}
        if self.truncation == "sliding_window":
            return {"strategy": "slidingWindow",
                    "config": {"slidingWindow": {"messagesCount": self.truncation_keep}}}
        return None

    def to_create_harness_kwargs(self, *, harness_name: str, execution_role_arn: str) -> dict:
        kw = {
            "harnessName": harness_name,
            "executionRoleArn": execution_role_arn,
            "model": self._model_block(),
            "systemPrompt": [{"text": self.system_prompt}],
            "tools": self._tool_blocks(),
            "maxIterations": self.max_iterations,
            "maxTokens": self.max_tokens,
        }
        trunc = self._truncation_block()
        if trunc:
            kw["truncation"] = trunc
        if self.skills:
            # The negotiation policy promotes to managed AgentCore as a skill. An
            # AgentCore skill is a DOCUMENT REFERENCE (path / s3 / git), not a bare
            # name -- so each skill maps to a file the deployer ships alongside the
            # harness (e.g. skills/<name>.md). The local executor folds the same
            # policy text straight into the system prompt instead.
            kw["skills"] = [{"path": f"skills/{s}.md"} for s in self.skills]
        return kw

    def to_invoke_harness_kwargs(self, *, harness_arn: str, session_id: str, messages: List[dict]) -> dict:
        return {
            "harnessArn": harness_arn,
            "runtimeSessionId": session_id,
            "messages": messages,
            "model": self._model_block(),
            "systemPrompt": [{"text": self.system_prompt}],
            "tools": self._tool_blocks(),
            "maxIterations": self.max_iterations,
            "maxTokens": self.max_tokens,
        }


# --------------------------------------------------------------------------- #
# Named configurations -- the experiment
# --------------------------------------------------------------------------- #

def _persona(role: str) -> str:
    return SELLER_PERSONA if role == "seller" else BUYER_PERSONA


def good_harness(role: str, model_id: str = SMALL_MODEL) -> HarnessConfig:
    sp = "\n\n".join([
        _persona(role),
        DEAL_SPACE_BLURB,
        # The engineered differentiator: a negotiation-policy SKILL the agent
        # reasons WITH (company guidelines), not a branch-per-scenario script.
        NEGOTIATION_SKILL,
        "HOW TO WORK A TURN (private, the other party never sees this):\n"
        "1. Reason about where a fair balance lies: think about how far the other "
        "party can move and what a deal both sides can live with looks like.\n"
        "2. Call calc_my_utility on any deal you're considering -- never do the "
        "arithmetic in your head; each concession is a pure transfer.\n"
        "3. Apply the negotiation policy above to the rounds-left and the current "
        "standing offer you are given, and decide whether to OFFER, ACCEPT, or WALK.\n"
        "4. Call validate_my_offer before sending; if it returns valid=false, fix "
        "the deal and try again.",
        # GOOD-specific output rule: tools FIRST, then commit. This must NOT say
        # "respond with only JSON" up front or the model skips tool calls. The
        # move shape itself is the SINGLE canonical OUTPUT_CONTRACT (same as every
        # other tier) so the validator/parser never disagree with the prompt.
        "TOOLS FIRST, THEN COMMIT:\n"
        "You have tools (calc_my_utility, validate_my_offer, my_batna). On a turn "
        "it is expected and correct to CALL TOOLS to analyze candidate deals. "
        "Only AFTER you have validated your chosen deal, produce your FINAL answer "
        "as your move. " + OUTPUT_CONTRACT,
    ])
    return HarnessConfig(
        kind=HarnessKind.GOOD, role=role, model_id=model_id, system_prompt=sp,
        tool_names=GOOD_TOOL_NAMES, truncation="summarization", truncation_keep=6,
        max_iterations=4, max_tokens=700, temperature=0.4, validate_gate=True,
        skills=("negotiation_policy",),
    )


def default_harness(role: str, model_id: str = SMALL_MODEL) -> HarnessConfig:
    """The PRE-BUILT scaffold tier: AgentCore's agent loop turned on, nothing tuned.

    This is the rung between RAW (no harness) and GOOD (engineered harness). It is
    the SAME config object and the SAME Strands engine as GOOD -- it just leaves the
    engineering fields at their out-of-the-box defaults:
      * persona + output contract (same as RAW), no task-specific coaching,
      * the inline tools ARE available and the multi-iteration tool loop IS on
        -- this is what a stock agent framework gives you for free, so the
        DEFAULT->GOOD gap isolates PURE engineering with capability held constant
        (DEFAULT is not a strawman: it has the exact same tools as GOOD),
      * framework-default memory (full context / NullConversationManager) -- GOOD's
        summarization is a DELIBERATE engineered choice, so it isn't baked in here,
      * NO theory-of-mind coaching prompt, NO validate/commit gate, and
        NO per-turn structured state hints (validate_gate stays False, so the
        executor and negotiate loop both skip those engineered steps automatically).

    So DEFAULT - RAW isolates "turn the agent framework on", and GOOD - DEFAULT
    isolates "engineer the config for the task". Same scaffold, different care."""
    sp = "\n\n".join([_persona(role), DEAL_SPACE_BLURB, OUTPUT_CONTRACT])
    return HarnessConfig(
        kind=HarnessKind.DEFAULT, role=role, model_id=model_id, system_prompt=sp,
        tool_names=GOOD_TOOL_NAMES, truncation="none",
        max_iterations=4, max_tokens=700, temperature=0.4, validate_gate=False,
    )


def raw_harness(role: str, model_id: str = LARGE_MODEL) -> HarnessConfig:
    sp = "\n\n".join([_persona(role), DEAL_SPACE_BLURB, OUTPUT_CONTRACT])
    return HarnessConfig(
        kind=HarnessKind.RAW, role=role, model_id=model_id, system_prompt=sp,
        tool_names=(), truncation="none", max_iterations=1, max_tokens=600, temperature=0.4,
    )


def bad_harness(role: str, model_id: str = LARGE_MODEL) -> HarnessConfig:
    sp = "\n\n".join([_persona(role), DEAL_SPACE_BLURB, GUARDRAIL_INJECTION, OUTPUT_CONTRACT])
    return HarnessConfig(
        kind=HarnessKind.BAD, role=role, model_id=model_id, system_prompt=sp,
        tool_names=(),                      # no calculator / validator
        truncation="sliding_window", truncation_keep=1,  # forgets all prior offers
        max_iterations=1, max_tokens=600, temperature=0.8, guardrail_overlay=True,
    )


def make_config(kind: HarnessKind, role: str, *, small=SMALL_MODEL, large=LARGE_MODEL) -> HarnessConfig:
    if kind == HarnessKind.GOOD:
        return good_harness(role, small)
    if kind == HarnessKind.DEFAULT:
        return default_harness(role, small)
    if kind == HarnessKind.RAW:
        return raw_harness(role, large)
    return bad_harness(role, large)


# --------------------------------------------------------------------------- #
# Move + per-turn result
# --------------------------------------------------------------------------- #

@dataclass
class Move:
    action: Optional[str]                 # OFFER | ACCEPT | WALK | None(=invalid)
    deal: Optional[Deal]
    message: str
    parse_ok: bool
    invalid: bool                         # offer failed parse/legality
    scratchpad: str = ""                  # private reasoning (shown only in trace viewer)
    tool_calls: List[dict] = field(default_factory=list)
    validator_bounces: int = 0            # GOOD harness: invalid offers caught before sending
    raw_text: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0


# --------------------------------------------------------------------------- #
# Executor: the real Strands Agents SDK as the orchestrator
# --------------------------------------------------------------------------- #
# Every tier -- RAW, DEFAULT, GOOD, BAD -- runs on the SAME engine: a Strands
# `Agent` (the exact open-source loop AgentCore Harness runs in its microVM). So
# the runtime is held CONSTANT and the only thing that varies is the
# HarnessConfig. That is what makes the ladder a clean ablation:
#   RAW     -> tool-less Agent, 1 turn               (bare model, "no harness")
#   DEFAULT -> Agent + tools + loop + default memory (the prebuilt scaffold)
#   GOOD    -> DEFAULT + ToM prompt + summarization  PLUS a code-based commit/
#              validate gate the executor wraps around the loop (engineered)
#   BAD     -> Agent, no tools, sliding-window-1 memory, output mangler (clumsy)
#
# The same HarnessConfig can be promoted to a managed AgentCore Harness via
# to_create_harness_kwargs()/to_invoke_harness_kwargs() + AgentCoreHarnessRunner
# (agentcore_runner.py) with no change to the config -- "same config, different
# runner". Strands here, managed InvokeHarness there.


def _strands_tool(name: str, role: str, recorder: List[dict]):
    """Wrap one INLINE_TOOLS entry as a Strands @tool, closing over the agent's
    role and recording each call so the trace viewer can show the pipeline.

    Strands derives a tool's input schema from the wrapped function's EXPLICIT
    signature and validates calls against it, so each tool gets a real
    typed signature (a **kwargs catch-all is rejected at invoke time)."""
    desc, _schema, impl = INLINE_TOOLS[name]

    def _record(args: dict) -> str:
        try:
            result = impl(role, args)
        except Exception as e:                # tool misuse is itself a signal
            result = json.dumps({"error": str(e)})
        recorder.append({"tool": name, "input": args, "result": result})
        return result

    if name == "my_batna":
        @tool(name=name, description=desc)
        def _fn() -> str:
            return _record({})
    else:
        # calc_my_utility / validate_my_offer share the candidate-deal signature.
        @tool(name=name, description=desc)
        def _fn(unit_price: float, payment_terms: str) -> str:
            return _record({"unit_price": unit_price, "payment_terms": payment_terms})

    return _fn


def _conversation_manager(cfg: HarnessConfig):
    """Map the config's truncation field onto a Strands ConversationManager.

    This is the SDK's real memory strategy -- not an approximation. The BAD
    harness's window of 1 is what makes it forget prior offers; GOOD's
    summarization is its deliberate rolling memory; DEFAULT/RAW keep full
    context (the framework default)."""
    if cfg.truncation == "summarization":
        return SummarizingConversationManager(
            summary_ratio=0.5, preserve_recent_messages=cfg.truncation_keep)
    if cfg.truncation == "sliding_window":
        return SlidingWindowConversationManager(window_size=cfg.truncation_keep)
    return NullConversationManager()


def _extract_scratchpad(agent: Agent, final_text: str) -> str:
    """Reconstruct the harness's private reasoning (the 'notepad' the trace
    viewer shows) from the agent's assistant text blocks this turn -- every text
    block EXCEPT the final committed move. Tool-use blocks are skipped; they're
    surfaced separately as the pipeline's tool calls."""
    parts: List[str] = []
    for m in agent.messages:
        if m.get("role") != "assistant":
            continue
        for c in m.get("content", []):
            txt = c.get("text") if isinstance(c, dict) else None
            if txt and txt.strip() and txt.strip() != final_text.strip():
                parts.append(txt.strip())
    return "\n".join(parts)


def _to_prompt_and_history(messages: List[dict]) -> Tuple[str, List[dict]]:
    """Split the public Converse-style message list into (current prompt, prior
    history) for a Strands Agent. The last user message is THIS turn's prompt;
    everything before it seeds Agent(messages=...)."""
    if not messages:
        return "Make your move.", []
    last = messages[-1]
    prompt = " ".join(c.get("text", "") for c in last.get("content", [])).strip()
    return (prompt or "Make your move.", messages[:-1])


class LocalHarnessExecutor:
    """Runs a HarnessConfig on a local Strands Agent (same SDK AgentCore uses).
    Builds a fresh Agent per turn from the config, runs the agent loop (tools +
    memory handled by Strands), then applies the harness-specific wrappers that
    live OUTSIDE the prebuilt loop: GOOD's commit/validate gate and BAD's
    output mangler. Preserves the run_turn(cfg, messages) -> Move seam so the
    negotiate loop / validate / server are unaffected."""

    def __init__(self, region: str = REGION):
        self._region = region

    def _price(self, model_id: str, usage: Dict[str, int]) -> float:
        pin, pout = MODEL_PRICING.get(model_id, (0.0, 0.0))
        return round(usage.get("inputTokens", 0) / 1000 * pin
                     + usage.get("outputTokens", 0) / 1000 * pout, 6)

    def _build_agent(self, cfg: HarnessConfig, history: List[dict],
                     recorder: List[dict]) -> Agent:
        model = BedrockModel(model_id=cfg.model_id, region_name=self._region,
                             temperature=cfg.temperature, max_tokens=cfg.max_tokens)
        tools = [_strands_tool(n, cfg.role, recorder) for n in cfg.tool_names]
        return Agent(
            model=model,
            system_prompt=cfg.system_prompt,
            tools=tools,
            messages=[dict(m) for m in history],
            conversation_manager=_conversation_manager(cfg),
            callback_handler=None,            # silence the SDK's stdout streaming
        )

    def _invoke(self, agent: Agent, prompt: str, cfg: HarnessConfig
                ) -> Tuple[str, Dict[str, int], float]:
        """Run the agent loop once; return (final_text, usage, cost).

        max_iterations bounds the model's TOOL-USE rounds (RAW/BAD = 1 = a single
        pass, no tools). The Strands `turns` cap counts every model call,
        including the final text commit AFTER the tool calls, so we add headroom;
        otherwise a tool-heavy GOOD turn would hit the cap mid-loop and emit no
        move. The cap is a runaway backstop, not the normal stop -- a well-behaved
        turn ends naturally (stop_reason 'end_turn') well under it."""
        turns = max(1, cfg.max_iterations)
        if cfg.tool_names:
            turns += 2                        # room to commit after the tool calls
        result = agent(prompt, limits=Limits(turns=turns))
        usage = dict(getattr(result.metrics, "accumulated_usage", {}) or {})
        usage = {"inputTokens": usage.get("inputTokens", 0),
                 "outputTokens": usage.get("outputTokens", 0)}
        return str(result).strip(), usage, self._price(cfg.model_id, usage)

    def run_turn(self, cfg: HarnessConfig, messages: List[dict]) -> Move:
        """messages: the public Converse-style message list for THIS agent's view."""
        prompt, history = _to_prompt_and_history(messages)
        recorder: List[dict] = []
        agg_usage = {"inputTokens": 0, "outputTokens": 0}
        cost = 0.0

        agent = self._build_agent(cfg, history, recorder)
        final_text, u, c = self._invoke(agent, prompt, cfg)
        agg_usage["inputTokens"] += u["inputTokens"]
        agg_usage["outputTokens"] += u["outputTokens"]
        cost += c

        # --- GOOD harness: commit + validate gate (code-based, OUTSIDE the loop) #
        # A config-based harness structurally cannot reject its own model's
        # output and retry; this is the engineered differentiator. If the move
        # fails to parse or fails validate_offer, re-prompt the SAME agent with
        # the reason and force a corrected move. Each bounce is an "invalid offer
        # the harness caught before sending" (RAW/BAD have no such gate).
        validator_bounces = 0
        if cfg.validate_gate:
            for _attempt in range(3):
                need_fix, reason = self._gate_check(final_text, cfg.role)
                if not need_fix:
                    break
                validator_bounces += 1
                fix_prompt = (
                    f"VALIDATOR REJECTED that offer: {reason}. Choose a LEGAL, "
                    "non-self-harming deal and reply with ONLY the JSON move "
                    "object, nothing else.")
                final_text, u, c = self._invoke(agent, fix_prompt, cfg)
                agg_usage["inputTokens"] += u["inputTokens"]
                agg_usage["outputTokens"] += u["outputTokens"]
                cost += c

            # Fallback: if the model still won't produce a legal, non-self-harming
            # move, the harness emits a SAFE legal anchor (the best in-ZOPA deal
            # for this role) rather than leak a bad offer. Guarantees a good
            # harness never sends a self-harming offer.
            need_fix, _ = self._gate_check(final_text, cfg.role)
            if need_fix:
                bs = bargaining_set()
                if bs:
                    key = seller_utility if cfg.role == "seller" else buyer_utility
                    safe = max(bs, key=key)
                    final_text = json.dumps({
                        "action": "OFFER", "deal": safe.as_dict(),
                        "message": "This is the best I can offer while staying viable."})
                    validator_bounces += 1

        # --- BAD harness output mangler ------------------------------------ #
        # An over-zealous compliance redactor occasionally strips the decisive
        # JSON, producing a format failure (a real cost of a clumsy guardrail).
        if cfg.guardrail_overlay and random.random() < GUARDRAIL_MANGLE_RATE:
            final_text = _mangle(final_text)

        action, deal, message, parse_ok = parse_move(final_text)
        invalid = not parse_ok
        scratch = _extract_scratchpad(agent, final_text)
        return Move(
            action=action, deal=deal, message=message, parse_ok=parse_ok, invalid=invalid,
            scratchpad=scratch, tool_calls=recorder, validator_bounces=validator_bounces,
            raw_text=final_text, usage=agg_usage, cost_usd=round(cost, 6),
        )

    @staticmethod
    def _gate_check(final_text: str, role: str) -> Tuple[bool, str]:
        """Return (need_fix, reason) for the GOOD harness's validate gate."""
        action, deal, _message, parse_ok = parse_move(final_text)
        if (not parse_ok) or action is None:
            return True, "your last message was not a single valid JSON move object"
        if action == "OFFER":
            ok, why = validate_offer(deal, role)
            if not ok:
                return True, why
        elif action == "ACCEPT":
            # A good harness must never ACCEPT a self-harming/illegal deal.
            if deal is None:
                return True, "ACCEPT must echo the deal you are accepting"
            ok, why = validate_offer(deal, role)
            if not ok:
                return True, f"do NOT accept that deal -- {why}. Counter or hold instead."
        return False, ""


def _mangle(text: str) -> str:
    """Simulate an over-aggressive guardrail redactor stripping decisive content."""
    return ("[[redacted by compliance overlay]] We might consider something "
            "reasonable, perhaps, though we can't commit to specifics right now.")
