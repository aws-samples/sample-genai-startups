# The Harness Pattern: What Happens When You Stop Defining Your Agents

*Draft for AWS Builder Blog , Agentic AI for Startups, EMEA*

---

There's a pattern emerging for building agentic systems without a great name yet. I've been calling it the meta agent (others call it harness), and once you see it, you start noticing it everywhere.

The idea is deceptively simple: instead of defining what your agent *is* , its role, its specialisation, its boundaries , you define what it *has access to*, and let it figure out the rest.

This post walks through a concrete example from a biotech research assistant I've been building with Claude Agent SDK, explains why this shift matters, and shares what I think it signals about where agentic AI is heading.

---

## The "old" way (~2025): defined agents

If you've built a multi-agent system in the last year or two, you probably started the same way most teams do. You decomposed the problem into roles. You gave each role a model, a prompt, a set of tools, and a name. Something like this:

```python
AGENTS = {
    "data-analyst": AgentDefinition(
        description="Statistician that analyzes datasets...",
        prompt="You are an expert data analyst. Think out loud...",
        tools=["Read", "Bash", "mcp__chembl__*", "mcp__opentargets__*"],
        model="sonnet",
    ),
    "literature-reviewer": AgentDefinition(
        description="Literature specialist that searches PubMed...",
        prompt="You are a biomedical literature expert...",
        tools=["Read", "mcp__pubmed__*", "mcp__biorxiv__*"],
        model="sonnet",
    ),
    "synthesizer": AgentDefinition(
        description="Research scientist that generates hypotheses...",
        prompt="You are a creative research scientist...",
        tools=["Read", "mcp__pubmed__*", "mcp__clinicaltrials__*"],
        model="opus",
    ),
}
```

Then you wired an orchestrator on top , using a smarter model, that read the data, delegated to each specialist, and synthesised a final report.

This feels natural. It mirrors how human research teams work. It's legible. You can point to each agent and explain what it does.

But it comes with hidden costs.

---

## What defined agents actually cost you

The first cost is rigidity. When you define an agent's role upfront, you're making a bet about how the problem should be decomposed. Sometimes that bet is right. Often it isn't , especially in research tasks where the interesting work happens at the boundaries between disciplines.

In the biotech example, the data analyst had access to ChEMBL and Open Targets. The literature reviewer had PubMed and bioRxiv. The synthesiser had ClinicalTrials and Open Targets. But what if the most important insight requires cross-referencing a PubMed abstract with a ChEMBL bioactivity record in the same reasoning step? You've just made that harder by design.

The second cost is coordination overhead. Every handoff between agents is a potential failure point. The orchestrator has to decide when to delegate, to whom, and with what context. The subagent has to interpret that context correctly. Results have to flow back and get integrated. Each of those steps can go wrong, and when they do, the failure mode is often subtle , the agent completes successfully but with a narrower view than the task required.

The third cost is prompt engineering debt. Three agents means three system prompts to maintain, three sets of tool permissions to reason about, and three mental models to keep in sync when the underlying tools or data change.

---

## The harness pattern

Here's what the same system looks like after collapsing the subagents:

```python
TOOLS = [
    "Read", "Write", "Bash", "Glob", "Grep",
    "mcp__pubmed__*", "mcp__chembl__*", "mcp__clinicaltrials__*",
    "mcp__biorxiv__*", "mcp__opentargets__*",
]
```

And the prompt:

```
You are a senior research scientist. Data files: {DATA_DIR}  Output dir: {OUTPUT_DIR}
You have tools for: file I/O, bash, PubMed, ChEMBL, ClinicalTrials.gov, bioRxiv, Open Targets.
Reason step by step: analyze data, search literature, then synthesize testable hypotheses.
Every citation must use real PMIDs/NCT IDs. Never fabricate references.
```

That's it. One agent. All tools. A clear task description and a few hard constraints.

The agent now decides for itself how to approach the problem. It might start by loading the assay CSV and running statistical comparisons across the three KRAS inhibitors. It might pivot to PubMed mid-analysis when it notices something unexpected in the data. 

You haven't told it how to do the research. You've given it the tools a researcher would need, and trusted it to reason through the problem.

---

## When the harness pattern works, and when it doesn't

Frontier models, especially with extended thinking enabled, have improved incredibly at self-organising around complex tasks. The structured approach was partly a workaround: when models struggled with long contexts, scoped subagents helped. When tool use was unreliable, smaller tool sets reduced the error surface. Those issues can still pop up, but they've shrunk enough that the coordination overhead of managing multiple agents often costs more than it saves.

That said, the harness isn't a universal replacement. It still has structure, just not role decomposition. You still need a clear task framing, hard constraints, and a defined output. What you're removing is the upfront bet about how the work should be divided.

| Use the harness | Stick with defined agents |
|---|---|
| Integrative tasks where reasoning crosses disciplines | Genuinely parallel workstreams that don't need shared context |
| You don't know upfront how data, literature, and synthesis connect | Task is too large for a single context window |
| | You need a clear audit trail of which "role" produced which output |

---

## What this means for startups building on AI

If you're building an AI-powered product right now, this pattern has a practical implication: your architecture should be as thin as you can make it.

The instinct when building agentic systems is to add structure , more agents, more roles, more orchestration logic. That structure feels like control. But a lot of it is actually compensating for model limitations that are eroding faster than your codebase is.

The teams I see moving fastest are the ones who treat their agent architecture as a hypothesis, not a commitment. They start simple, observe where the model gets stuck, and add structure only where the evidence demands it. They're also evolving them constantly.

The biotech example is a small illustration of a bigger shift. The question is no longer "how do I decompose this task across agents?" It's "what does this agent need access to, and what does it need to know?" Everything else is overhead until proven otherwise.

---

## Try it yourself

The full example , including the original multi-agent version and the harness refactor , is available in the [AWS Samples repository](https://github.com/aws-samples). The dataset is 30 rows of simulated KRAS inhibitor assay data. This is meant to illustrate this comparison and not to be used as a full agent implementation.

Try it with this prompt:

```bash
python run.py "What combination therapy strategies show the most promise for KRAS G12C inhibitors?"
```

Watch how the agent navigates the problem. Notice what it chooses to do first, where it reaches for literature versus data, how it connects the findings to the clinical trial landscape. That reasoning trace is the interesting part , not the architecture that produced it.

---

*The views expressed here are my own. All AI-generated outputs in the example require expert human review before use in any research or clinical context.*
