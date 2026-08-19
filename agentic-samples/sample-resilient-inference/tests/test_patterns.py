import os
import unittest
from unittest.mock import MagicMock, patch

from examples.stage3_gateway_probe import probe_gateway
from examples.stage3_production import invoke
from reliable_inference import (
    Draft,
    EvalCase,
    GatewaySettings,
    build_gateway_ticket_agent,
    draft_reply as call_ticket_agent,
    load_gateway_settings,
    score,
)


CASE = EvalCase(
    name="order status",
    ticket="Where is order #10042?",
    order_context="Order #10042 shipped.",
    required_terms=("#10042", "shipped"),
    allowed_order_ids=frozenset({"10042"}),
)


def draft(text: str) -> Draft:
    return Draft(
        text=text,
        model_id="test-model",
        latency_ms=10,
        input_tokens=20,
        output_tokens=10,
        stop_reason="end_turn",
    )


class AgentCallTests(unittest.TestCase):
    def test_draft_reply_returns_agent_usage(self) -> None:
        result = MagicMock()
        result.__str__.return_value = "Order #10042 shipped."
        result.stop_reason = "end_turn"
        result.metrics.get_summary.return_value = {
            "accumulated_usage": {"inputTokens": 20, "outputTokens": 10}
        }

        with patch("reliable_inference.core.build_ticket_agent", return_value=lambda _: result):
            response = call_ticket_agent(
                "Where is order #10042?",
                "Order #10042 shipped.",
                model_id="test-model",
            )

        self.assertEqual(response.text, "Order #10042 shipped.")
        self.assertEqual(response.input_tokens, 20)
        self.assertEqual(response.output_tokens, 10)
        self.assertEqual(response.stop_reason, "end_turn")


class EvaluationTests(unittest.TestCase):
    def test_valid_reply_passes(self) -> None:
        outcome = score(CASE, draft("Order #10042 has shipped."))
        self.assertTrue(outcome.passed)

    def test_invented_order_fails(self) -> None:
        outcome = score(CASE, draft("Order #99999 has shipped."))
        self.assertIn("invented order ID", outcome.violations)

    def test_refund_authorization_fails(self) -> None:
        outcome = score(CASE, draft("I issued a refund for order #10042, which shipped."))
        self.assertIn("authorized a refund", outcome.violations)

    def test_missing_required_fact_fails(self) -> None:
        outcome = score(CASE, draft("I found order #10042."))
        self.assertIn("missing required term: shipped", outcome.violations)

    def test_required_action_passes(self) -> None:
        case = EvalCase(
            name="unknown order",
            ticket="Where is order #99999?",
            order_context="No matching order was found.",
            required_terms=("#99999", "verify"),
            allowed_order_ids=frozenset({"99999"}),
        )
        outcome = score(case, draft("Please verify order #99999."))
        self.assertTrue(outcome.passed)

    def test_missing_required_action_fails(self) -> None:
        case = EvalCase(
            name="unknown order",
            ticket="Where is order #99999?",
            order_context="No matching order was found.",
            required_terms=("#99999", "verify"),
            allowed_order_ids=frozenset({"99999"}),
        )
        outcome = score(case, draft("Order #99999 was not found."))
        self.assertIn("missing required term: verify", outcome.violations)


class GatewayTests(unittest.TestCase):
    def test_gateway_agent_calls_stable_alias(self) -> None:
        settings = GatewaySettings(
            base_url="http://gateway.example",
            api_key="test-key",
            model_alias="ticket-drafter",
        )
        with (
            patch("reliable_inference.gateway.LiteLLMModel") as model,
            patch("reliable_inference.gateway.Agent") as agent,
        ):
            build_gateway_ticket_agent(settings)

        model.assert_called_once_with(
            client_args={
                "api_base": "http://gateway.example",
                "api_key": "test-key",
                "use_litellm_proxy": True,
                "num_retries": 0,
                "timeout": 35,
            },
            model_id="ticket-drafter",
            params={"max_tokens": 300, "temperature": 0},
            stream=False,
        )
        agent.assert_called_once()

    def test_runtime_can_load_gateway_key_from_secrets_manager(self) -> None:
        secret_client = MagicMock()
        secret_client.get_secret_value.return_value = {"SecretString": "gateway-key"}
        with (
            patch.dict(
                os.environ,
                {
                    "LITELLM_API_KEY_SECRET_ID": "ticket-gateway-key",
                    "LITELLM_BASE_URL": "https://gateway.example",
                },
                clear=True,
            ),
            patch(
                "reliable_inference.gateway._secrets_client",
                return_value=secret_client,
            ),
        ):
            settings = load_gateway_settings()

        self.assertEqual(settings.api_key, "gateway-key")
        secret_client.get_secret_value.assert_called_once_with(
            SecretId="ticket-gateway-key"
        )

    def test_runtime_handler_reports_gateway_alias(self) -> None:
        gateway_draft = draft("Order #10042 shipped.")
        gateway_draft = Draft(
            text=gateway_draft.text,
            model_id="ticket-drafter",
            latency_ms=gateway_draft.latency_ms,
            input_tokens=gateway_draft.input_tokens,
            output_tokens=gateway_draft.output_tokens,
            stop_reason=gateway_draft.stop_reason,
        )
        with patch(
            "examples.stage3_production.draft_reply_via_gateway",
            return_value=gateway_draft,
        ):
            result = invoke(
                {
                    "ticket": "Where is order #10042?",
                    "order_context": "Order #10042 shipped.",
                }
            )

        self.assertEqual(result["route_alias"], "ticket-drafter")
        self.assertNotIn("fallback_used", result)

    def test_gateway_probe_reports_fallback_deployment(self) -> None:
        response = MagicMock()
        response.model = "us.amazon.nova-micro-v1:0"
        response.choices = [MagicMock(message=MagicMock(content="Order #10042 shipped."))]
        raw_response = MagicMock()
        raw_response.headers = {"x-litellm-model-id": "ticket-drafter-fallback"}
        raw_response.parse.return_value = response
        client = MagicMock()
        client.chat.completions.with_raw_response.create.return_value = raw_response

        result = probe_gateway(
            "Where is order #10042?",
            "Order #10042 shipped.",
            settings=GatewaySettings("http://gateway.example", "test-key"),
            client=client,
        )

        self.assertTrue(result.fallback_used)
        self.assertEqual(result.deployment_id, "ticket-drafter-fallback")

    def test_stage3_rejects_missing_context(self) -> None:
        with self.assertRaisesRegex(ValueError, "payload.order_context"):
            invoke({"ticket": "Where is order #10042?"})


if __name__ == "__main__":
    unittest.main()
