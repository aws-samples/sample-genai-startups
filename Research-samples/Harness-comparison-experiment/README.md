# Bazaar-80 Public

Bazaar-80 is a small Amazon Bedrock experiment about a simple question:

> How much does agent behavior move when you keep the model fixed and change only the harness?

The project uses a zero-sum negotiation game. Two traders haggle over one 300-widget order. The seller moves through **NO HARNESS**, **PREBUILT HARNESS**, **ENGINEERED HARNESS**, and one deliberately poor configuration, **BAD HARNESS**. The framing follows [Harness-Bench](https://arxiv.org/html/2605.27922v1): capability is a property of the model and the harness together.

This public version contains the runnable code, the replay UI, and the experiment docs. It leaves out the presentation-specific material from the working repo.

> Warning: This sample is for illustration and experimentation only. It is not production-ready and should not be deployed or used in production environments as-is.

## What is in here

- `bazaar80/`: core package with game logic, harness configs, prompts, scenarios, and the negotiation loop
- `scripts/validate.py`: batch experiment runner
- `scripts/bundle_traces.py`: packs saved traces into `web/traces.js` for replay
- `scripts/server.py`: optional local backend for streaming a live Bedrock run
- `web/`: static replay UI plus a bundled replay dataset
- `skills/negotiation_policy.md`: the reusable policy text used by the engineered harness
- `EXPERIMENT.md`: the short reproducible write-up for the `Aggressive Opener` experiment

## Harness ladder

The seller runs in one of four configurations:

- `NO HARNESS` (`RAW`): bare model, one pass, no tools
- `PREBUILT HARNESS` (`DEFAULT`): prebuilt scaffold with tools and a multi-step loop
- `ENGINEERED HARNESS` (`GOOD`): summarized memory, state hints, negotiation skill, and a commit/validate gate
- `BAD HARNESS` (`BAD`): clumsy guardrail overlay, tiny memory window, and format drift

The buyer stays fixed so the seller harness is the main variable.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Run the main experiment:

Warning: this command runs live Bedrock inference and can incur AWS charges.

```bash
python scripts/validate.py --scenario anchor_war -n 8 --save-traces
```

To grow the replay pool without overwriting existing files, use
`python scripts/validate.py --scenario anchor_war --save-traces --target 20`.
This also runs live Bedrock inference and can incur AWS charges.

Rebuild the replay bundle and open the static UI:

```bash
python scripts/bundle_traces.py
open web/index.html
```

For the simplified `Aggressive Opener / LOWBALL` replay used in the article:

```bash
open web/index_v2.html
```
That view exposes `small+RAW`, `small+DEFAULT`, `small+GOOD`, `large+GOOD`, and `large+BAD`.

To stream a fresh Bedrock run through a local backend:

Warning: starting the backend is local, but using the live-run path triggers live Bedrock inference and can incur AWS charges.

```bash
pip install -r requirements-server.txt
python scripts/server.py
```

Then open `http://127.0.0.1:8080`.

## Scenarios

- `anchor_war`: Aggressive Opener (`LOWBALL` in `web/index_v2.html`)
- `tight_window`: Narrow Margin / closing pressure
- `fine_print`: Hidden Value / calculation pressure
- `marathon`: optional long-horizon memory case

## Notes

- Bedrock calls are live. You need AWS credentials with Bedrock access in `us-west-2`.
- This sample is not intended for production use. Add your own security, safety, observability, failure handling, and cost controls before considering any production adaptation.
- `web/traces.js` is already included so the replay UI works without generating new traces first.
- `web/index.html` is the full replay matrix. `web/index_v2.html` is the simplified Aggressive Opener / LOWBALL view.
- If you want the experiment framing and numbers behind the featured scenario, start with [EXPERIMENT.md](EXPERIMENT.md).
