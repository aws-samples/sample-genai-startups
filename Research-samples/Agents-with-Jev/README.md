# Jev shared semantic incident agent

> **Sample code:** This project is a proof of concept for learning and
> experimentation. It is not production-ready and has not been hardened for
> security, reliability, scale, or operational use.

This project implements a complete shared-semantic-state flow:

```text
Incident evidence
       |
       v
GPT-5.6 Sol extraction
       |
       v
Jev bounded judgments
       |
       v
Deterministic resolver
       |
       v
DynamoDB shared state
       |
       v
Strands incident agent
```

The incident agent reads resolved state through tools rather than interpreting
the source messages independently. Claims with low semantic confidence remain
pending review and do not replace accepted state.

## Full use case

Create the on-demand DynamoDB table:

```bash
incident-agent setup
```

Compile the evidence fixtures into shared state:

```bash
incident-agent ingest
```

Inspect current state and claim history:

```bash
incident-agent show --service checkout-api
```

Include raw Jev probabilities when debugging:

```bash
incident-agent show --service checkout-api --diagnostics
```

Ask the Strands agent:

```bash
incident-agent ask --service checkout-api \
  "What happened, what is the confirmed cause, and what remains uncertain?"
```

Run setup, ingestion, and the example question together:

```bash
incident-agent demo
```

Evidence ingestion is idempotent. To rebuild one service after changing the
semantic contract:

```bash
incident-agent rebuild --service checkout-api
```

The default table is `jev-semantic-state`. It uses:

```text
SERVICE#<service> / CURRENT#INCIDENT
SERVICE#<service> / EVIDENCE#<time>#<id>
SERVICE#<service> / CLAIM#<time>#<id>
```

The agent exposes three tools:

- `get_incident_state`
- `get_incident_timeline`
- `get_incident_evidence`

## Setup

```bash
cd Research-samples/Agents-with-Jev
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

Configure AWS credentials using the standard AWS credential chain and place a
TypeSafe API key in `TYPESAFE_API_KEY`.

The default frontier model is:

```text
global.openai.gpt-5.6-sol
```

The Strands `OpenAIModel` routes it through the Bedrock OpenAI-compatible
`bedrock-runtime` endpoint.
