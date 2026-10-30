# Production Readiness Checklist

Evaluate every agent implementation against these items. Each item maps to a severity level.

## Security (CRITICAL)

- [ ] **Input validation layer**: System prompt or guardrails config includes input filtering (content filters, denied topics, or explicit validation instructions). Missing = prompt injection risk.
- [ ] **Least-privilege tool permissions**: Agent tools are scoped to minimum required access (e.g., read-only DB, specific API actions). Overly broad = data exposure risk.
- [ ] **Output validation**: Agent responses pass through output guardrails or filtering before reaching users. Missing = PII leakage and hallucinated policy risk.
- [ ] **Hardcoded secrets**: Check for API keys, credentials, or tokens embedded in code, configs, or prompts. Flag every one you find, quoting file and line. Confirm the implementation instead reads them at runtime from environment variables or a managed secrets store.
- [ ] **Scope boundaries in prompt**: System prompt explicitly states what the agent must NOT do (e.g., "do not access table X", "do not send emails without confirmation").

## Cost Guardrails (WARNING)

- [ ] **Loop circuit breaker**: Max iterations or max turns configured to prevent runaway agent loops. Missing = unbounded cost risk.
- [ ] **Cost alerting**: Budget alerts, cost anomaly detection, or per-session spending limits configured. Missing = surprise bills.
- [ ] **Retry with backoff**: API calls and tool invocations include retry logic with exponential backoff. Missing = cascading failures on throttling.
- [ ] **Fallback strategy**: Agent has a defined behavior when tools fail or models throttle (e.g., human escalation, graceful degradation). Missing = silent failures.
- [ ] **Timeout configuration**: Tool calls and agent sessions have timeout limits. Missing = hung sessions consuming resources.

## Observability (WARNING)

- [ ] **Distributed tracing**: X-Ray, OpenTelemetry, or equivalent tracing enabled for agent invocations. Missing = blind to failure chains.
- [ ] **Structured logging**: Agent logs include request IDs, tool call details, and error context in structured format. Missing = impossible to debug.
- [ ] **Metrics and alarms**: CloudWatch metrics or equivalent for agent latency, error rate, and token usage. Missing = no early warning.
- [ ] **Audit trail**: Agent actions (especially tool calls that modify state) are logged for compliance. Missing = accountability gap.

## Responsible AI (WARNING)

- [ ] **Content filtering**: Bedrock Guardrails or equivalent content filters configured for both input and output. Missing = harmful content risk.
- [ ] **Denied topics**: Topics the agent must refuse to discuss are explicitly configured. Missing = off-topic or dangerous responses.
- [ ] **Hallucination mitigation**: Agent is instructed to cite sources, say "I don't know", or use grounding (RAG). Missing = confident wrong answers.
- [ ] **Human-in-the-loop**: Destructive or high-impact actions require user confirmation. Missing = autonomous damage.

## Reliability (WARNING)

- [ ] **Error handling**: Tool failures are caught and produce meaningful error messages rather than crashing. Missing = poor user experience.
- [ ] **Graceful degradation**: Agent can still provide partial value when some tools or services are unavailable. Missing = all-or-nothing fragility.
- [ ] **Idempotency**: State-modifying operations are idempotent or have deduplication. Missing = duplicate actions on retry.
- [ ] **Rate limiting awareness**: Agent respects API rate limits and implements throttling. Missing = account-level throttling.
