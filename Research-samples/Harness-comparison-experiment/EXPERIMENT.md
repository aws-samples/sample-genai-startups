# Experiment: Aggressive Opener

This is the public, shareable version of the core experiment behind Bazaar-80. It uses the same framing as [Harness-Bench](https://arxiv.org/html/2605.27922v1): agent behavior is a property of the model and the harness together.

The question is simple:

> If you keep the model fixed and change only the harness, how much does the result move?

The featured case is **Aggressive Opener**. In the code, the scenario id is `anchor_war`. The full replay matrix uses `AGGRESSIVE OPENER`; the simplified single-scenario view (`web/index_v2.html`) labels the same case `LOWBALL`.

## Hypothesis

Agent performance is a property of the **model x harness** configuration, not the base model alone.

In this project, the expected pattern is:

- `NO HARNESS -> PREBUILT HARNESS` gives the biggest reliable lift
- `PREBUILT HARNESS -> ENGINEERED HARNESS` can improve outcome further when the task and model can use the extra structure
- `BAD HARNESS` shows that adding the wrong scaffold can still make the agent worse

## Controlled setup

The experiment holds these factors constant:

- same game: one 300-widget negotiation
- same scenario: `anchor_war`
- same runtime: local Strands Agents executor
- same Bedrock region: `us-west-2`
- same buyer: fixed small-model no-harness opponent (`RAW` in code)

The main independent variable is the **seller harness**:

| Seller config | Description |
|---|---|
| `NO HARNESS` (`RAW`) | bare model, one pass, no tools |
| `PREBUILT HARNESS` (`DEFAULT`) | tools plus agent loop, no task tuning |
| `ENGINEERED HARNESS` (`GOOD`) | summarized memory, state hints, negotiation skill, commit/validate gate |
| `BAD HARNESS` (`BAD`) | clumsy guardrail overlay, tiny memory window, no useful tools |

The two model sizes used here are:

- small: `us.amazon.nova-2-lite-v1:0`
- large: `us.anthropic.claude-sonnet-4-6`

## How to run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python scripts/validate.py --scenario anchor_war -n 8 --save-traces
```

To grow the replay pool without overwriting existing files, use
`python scripts/validate.py --scenario anchor_war --save-traces --target 20`.

Optional replay bundle:

```bash
python scripts/bundle_traces.py
open web/index.html
```

For the simplified `Aggressive Opener / LOWBALL` replay:

```bash
open web/index_v2.html
```
That view exposes `small+RAW`, `small+DEFAULT`, `small+GOOD`, `large+GOOD`, and `large+BAD`.

## Representative Aggressive Opener result

One representative post-fix `anchor_war` sweep produced these numbers:

| Seller cell | Mean seller surplus | Deal rate |
|---|---:|---:|
| Small + `NO HARNESS` (`small+RAW`) | 300 | 0.0% |
| Small + `PREBUILT HARNESS` (`small+DEFAULT`) | 472 | 87.5% |
| Small + `ENGINEERED HARNESS` (`small+GOOD`) | 525 | 62.5% |
| Frontier + `NO HARNESS` (`large+RAW`) | 480 | 75.0% |
| Frontier + `PREBUILT HARNESS` (`large+DEFAULT`) | 510 | 87.5% |
| Frontier + `ENGINEERED HARNESS` (`large+GOOD`) | 548 | 87.5% |
| Frontier + `BAD HARNESS` (`large+BAD`) | 506 | 62.5% |

What that says:

- The small model depends heavily on the harness. `NO HARNESS` fails to close, `PREBUILT HARNESS` makes it viable, and `ENGINEERED HARNESS` improves average claim while giving up some deal rate.
- The larger model also benefits from the ladder, but the gains are smaller because the base model is already stronger.
- `BAD HARNESS` is the warning case: a harness does not have to be absent to hurt you.

## Why this experiment is useful

This code supports a narrower and more useful claim than "one harness always wins":

- a framework scaffold is a real capability boost
- extra engineering can help, but only when it matches the task
- harness bugs and harness design choices are first-class failure surfaces

If you want to inspect the implementation, start with:

- [bazaar80/harness.py](bazaar80/harness.py)
- [bazaar80/scenarios.py](bazaar80/scenarios.py)
- [scripts/validate.py](scripts/validate.py)
