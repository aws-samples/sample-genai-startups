# Day-2 operations (optional follow-on after migration)

Load only when the user asks about operating the migrated agent: observability,
cost, resilience, security hardening, or latency/cold starts.

## Observability — four signals

Metrics, logs, traces, **+ evaluations** — the one teams skip; an agent can be
available and wrong. Enable CloudWatch Transaction Search once per account/Region;
configure Vended Logs delivery; Runtime auto-instruments OTel (OTLP forwards to
Datadog/Langfuse/etc.). Use a structured session-ID scheme (`{user}_{ts}_{purpose}`).
Enrich spans (token counts for billing) via Strands lifecycle hooks. Bedrock in-stream
trace consumers need real rework (in-memory OTel span exporter mapping to your schema
tends to work).

## Cost levers (highest first)

Model routing (small→large, ~30–60%); prompt caching (breakpoint after system prompt +
tool defs); batch inference (~50% for non-real-time); sample telemetry. Idle I/O-wait
inside a session still bills.

## Resilience (layered)

Adaptive retry w/ backoff (NOT for content-filter — not retryable); circuit breaker
per dependency; fallback model routing (pre-validate against the eval set); CRIS +
multi-Region for DR (mind residency); graceful degradation. Standardize tool error
payloads to prevent retry storms.

## Security

Least-privilege exec role on specific model ARNs; Guardrails Shadow → ENFORCE; Cedar
tool-authorization is the only adversarially-robust prompt-injection layer; sanitize
tool outputs before re-feeding the model; encode tenant in Cognito claim + Cedar
attribute.

## Latency / cold starts

Code deploy = lower baseline but **no pre-warm pool**; container = higher baseline but
**per-endpoint pre-warmed instances**. Slim the artifact; defer/lazy-init heavy work
incl. **Gateway/MCP client + token exchange**; **reuse session IDs** within the idle
window (default 15 min); pre-warm via a strategic ping; a **warmup sentinel**
(entrypoint returns on `{"type":"warmup"}` before any model/tool call). Capacity unit
= **concurrent sessions**, not RPS. Use p95/p99.
